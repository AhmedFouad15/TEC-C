from datetime import datetime, timezone

from tecc_brain.market import SnapshotSource
from tecc_brain.models import NewsSignal
from tecc_brain.reference import load_reference
from tecc_brain.sentinel.blended import (
    CMC_MACRO_WEIGHT,
    COINGLASS_MACRO_WEIGHT,
    COINGLASS_TOKEN_WEIGHT,
    FINBERT_TOKEN_WEIGHT,
    GROK_MACRO_WEIGHT,
    GROK_TOKEN_WEIGHT,
    NewsRiskSentinel,
)
from tecc_brain.sentinel.cmc_feargreed import CmcFearGreedClient, FearGreedReading
from tecc_brain.sentinel.coinglass import CoinGlassClient, CoinGlassTokenMetrics
from tecc_brain.sentinel.grok import GrokMacroRubric, GrokSentinel, GrokTokenRubric


def test_fear_greed_contrarian_vice_versa_scale():
    """Verifies that CMC Fear & Greed uses the contrarian ('vice versa') scale:
    - Extreme Greed (100) -> motivated to sell -> 0.0 (strong sell)
    - Extreme Fear (0) -> motivated to buy -> 1.0 (strong buy)
    - Neutral (50) -> 0.5 (neutral)
    """
    now = datetime.now(timezone.utc)

    # Extreme greed -> sell
    greed_100 = FearGreedReading(value=100, classification="Extreme Greed", as_of=now)
    assert greed_100.buy_sell_score == 0.0

    # High greed (80) -> sell
    greed_80 = FearGreedReading(value=80, classification="Greed", as_of=now)
    assert round(greed_80.buy_sell_score, 2) == 0.20

    # Neutral (50) -> neutral
    neutral_50 = FearGreedReading(value=50, classification="Neutral", as_of=now)
    assert neutral_50.buy_sell_score == 0.50

    # High fear (20) -> buy
    fear_20 = FearGreedReading(value=20, classification="Fear", as_of=now)
    assert round(fear_20.buy_sell_score, 2) == 0.80

    # Extreme fear (0) -> buy
    fear_0 = FearGreedReading(value=0, classification="Extreme Fear", as_of=now)
    assert fear_0.buy_sell_score == 1.0


def test_fear_greed_sigmoid_tail_amplification_and_velocity_boost():
    """Verifies:
    1. Noise band (40..60) is suppressed towards 0.50.
    2. Extreme fear (<20) is amplified towards 1.0.
    3. Velocity Boost: When fear turns up (e.g. 12 yesterday -> 16 today), +0.10 reversal boost.
    """
    now = datetime.now(timezone.utc)

    # 1. Noise suppression between 40 and 60
    reading_55 = FearGreedReading(value=55, classification="Neutral", as_of=now)
    # f_inv is 0.45, compressed towards 0.50: 0.50 + (0.45 - 0.50)*0.4 = 0.48
    assert reading_55.amplified_buy_sell_score == 0.48

    # 2. Extreme fear amplified
    reading_15 = FearGreedReading(value=15, classification="Extreme Fear", as_of=now)
    # f_inv is 0.85 -> amplified +0.08 = 0.93
    assert reading_15.amplified_buy_sell_score == 0.93

    # 3. Velocity boost: Panic exhausting (12 -> 16 today)
    reversal = FearGreedReading(value=16, classification="Extreme Fear", as_of=now, prev_value=12, delta_24h=4)
    # Base amplified: 0.84 + 0.08 = 0.92, plus velocity boost +0.10 = 1.00 (clamped)
    assert reversal.amplified_buy_sell_score == 1.0


def test_cmc_client_fallback_to_neutral():
    """When CMC_API_KEY is unset, client must safely degrade to 0.5 neutral reading."""
    client = CmcFearGreedClient(api_key=None)
    reading = client.fetch()
    assert reading.value == 50
    assert reading.classification == "Neutral"
    assert reading.buy_sell_score == 0.50
    assert "fallback" in reading.source


def test_grok_structured_x_pulse_macro_and_token():
    """Verifies Grok structured X-sentiment decomposition:
    - Macro: clip(0.5 + (Capitulation - Euphoria) / 200, 0, 1)
    - Token: Retail contrarian + security tracker
    """
    # High capitulation (80), low euphoria (10) -> (80-10)/200 = +0.35 -> 0.85 contrarian buy
    capitulation_rubric = GrokMacroRubric(retail_capitulation_index=80, retail_euphoria_index=10)
    assert capitulation_rubric.macro_score == 0.85

    # High euphoria (90), low capitulation (10) -> (10-90)/200 = -0.40 -> 0.10 contrarian sell
    euphoria_rubric = GrokMacroRubric(retail_capitulation_index=10, retail_euphoria_index=90)
    assert euphoria_rubric.macro_score == 0.10

    # Token rubric: Retail panic (70 vs 20 FOMO) -> 0.5 + 50/200 = 0.75
    token_rubric = GrokTokenRubric(symbol="USDC", retail_panic_index=70, retail_fomo_index=20)
    assert token_rubric.token_score == 0.75

    # If security alert detected -> slashed to 0.0
    hacked_token = GrokTokenRubric(symbol="stETH", security_alert_detected=True, security_details="Exploit report on X")
    assert hacked_token.token_score == 0.0


def test_coinglass_microstructure_and_macro_flush():
    """Verifies CoinGlass 4 microstructure metrics and macro flush confirmation."""
    cg = CoinGlassClient(api_key=None)

    # 1. Macro flush: baseline
    flush = cg.macro_flush()
    assert 0.0 <= flush.macro_score <= 1.0

    # 2. Token microstructure 4 metrics:
    # Leveraged longs flushed out: Price down, OI drops sharp (>10%) -> Bullish (0.85)
    # Deeply negative funding rate (< -0.02%) -> Bullish (0.90)
    # Top traders long (> 1.5) + retail short (< 0.8) -> Strong Buy (0.95)
    # Spot CVD positive + perp CVD negative -> Strong Buy (0.90)
    metrics = CoinGlassTokenMetrics(
        symbol="USDC",
        delta_oi_24h=-0.15,
        delta_price_24h=-0.04,
        funding_rate_8h=-0.0003,
        top_trader_ls_ratio=1.70,
        retail_ls_ratio=0.70,
        spot_cvd_usd=50_000_000.0,
        perp_cvd_usd=-30_000_000.0,
    )
    report = metrics.score()
    assert report.oi_price_score == 0.85
    assert report.funding_score == 0.90
    assert report.whale_retail_score == 0.95
    assert report.cvd_score == 0.90
    assert report.composite_score == 0.90


def test_upgraded_market_statement_pipeline():
    """Pipeline 1: Macro Score M = 0.35 * CMC + 0.35 * Grok_Macro + 0.30 * CoinGlass_Macro."""
    ref = load_reference()
    snapshot = SnapshotSource("demo").snapshot()
    sentinel = NewsRiskSentinel(ref=ref)

    report = sentinel.assess(snapshot, ref)
    ms = report.market_statement

    expected_macro = round(
        CMC_MACRO_WEIGHT * ms.cmc_score
        + GROK_MACRO_WEIGHT * ms.grok_score
        + COINGLASS_MACRO_WEIGHT * ms.coinglass_score,
        3,
    )
    assert ms.market_buy_sell_score == expected_macro
    assert report.overall_buy_sell_score == expected_macro


def test_upgraded_token_check_and_gate_0_veto():
    """Pipeline 2:
    - Clean state: S_Token = 0.45 * C_CoinGlass + 0.30 * F_FinBERT + 0.25 * G_Grok
    - GATE 0 Veto: Insolvency/exploit headline with high negative probability forces I_Safe = 0, S_Token = 0.0 (Immediate Sell)
    """
    ref = load_reference()
    snapshot = SnapshotSource("demo").snapshot()
    sentinel = NewsRiskSentinel(ref=ref)

    # 1. Clean run without exploit headlines
    report_clean = sentinel.assess(snapshot, ref)
    usdc_clean = report_clean.assets["USDC"]
    assert usdc_clean.token_check.gate_safe == 1
    assert usdc_clean.token_check.token_buy_sell_score > 0.0

    # 2. Inject structural insolvency trigger headline: "stETH de-peg exploit drained pool bankruptcy"
    exploited_news = NewsSignal(
        entity="stETH",
        p_negative=0.95,
        headline="stETH major de-peg exploit drained pool and halted redemptions in insolvency crisis",
        source="breaking",
    )
    snapshot_exploited = snapshot.model_copy(update={"news": [*snapshot.news, exploited_news]})

    report_exploited = sentinel.assess(snapshot_exploited, ref)
    steth_asset = report_exploited.assets["stETH"]
    tc = steth_asset.token_check

    # GATE 0 Hard Circuit Breaker must trigger:
    assert tc.gate_safe == 0
    assert tc.token_buy_sell_score == 0.0  # Forced 0.0 (Immediate Sell / Do Not Enter)
    assert steth_asset.buy_sell_score == 0.0
    assert steth_asset.p_negative == 1.0  # Trips max negative sentiment
    assert "Veto" in tc.veto_reason

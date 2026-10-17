from datetime import datetime, timezone

from tecc_brain.market import SnapshotSource
from tecc_brain.reference import load_reference
from tecc_brain.sentinel.blended import NewsRiskSentinel
from tecc_brain.sentinel.cmc_feargreed import CmcFearGreedClient, FearGreedReading
from tecc_brain.sentinel.grok import GrokSentinel


def test_fear_greed_contrarian_vice_versa_scale():
    """Verifies that CMC Fear & Greed uses the contrarian ('vice versa') scale per project spec:
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


def test_cmc_client_fallback_to_neutral():
    """When CMC_API_KEY is unset, client must safely degrade to 0.5 neutral reading."""
    client = CmcFearGreedClient(api_key=None)
    reading = client.fetch()
    assert reading.value == 50
    assert reading.classification == "Neutral"
    assert reading.buy_sell_score == 0.50
    assert "fallback" in reading.source


def test_grok_market_sentiment_contrarian_fallback():
    """Grok market sentiment without API key must return 0.5 neutral fallback."""
    ref = load_reference()
    grok = GrokSentinel(ref, api_key=None)
    score = grok.market_sentiment()
    assert score == 0.50


def test_two_fifty_fifty_formulas_in_sentinel():
    """Verifies that NewsRiskSentinel implements both 50/50 formulas exactly:
    Formula 1: Market Statement = 50% CMC Fear & Greed + 50% Grok Macro Sentiment
    Formula 2: Token Check = 50% Grok Asset Sentiment + 50% FinBERT News Sentiment
    """
    ref = load_reference()
    snapshot = SnapshotSource("demo").snapshot()
    sentinel = NewsRiskSentinel(ref=ref)
    
    report = sentinel.assess(snapshot, ref)
    
    # 1. Formula 1: Market Statement
    ms = report.market_statement
    expected_market = round(0.5 * ms.cmc_score + 0.5 * ms.grok_score, 3)
    assert ms.market_buy_sell_score == expected_market
    assert report.overall_buy_sell_score == expected_market

    # 2. Formula 2: Token Check on each peg
    for symbol, asset in report.assets.items():
        assert asset.token_check is not None
        tc = asset.token_check
        expected_token = round(0.5 * tc.grok_score + 0.5 * tc.finbert_score, 3)
        assert tc.token_buy_sell_score == expected_token
        # Asset combined score combines market statement + token check
        expected_combined = round(0.5 * ms.market_buy_sell_score + 0.5 * tc.token_buy_sell_score, 3)
        assert asset.buy_sell_score == expected_combined

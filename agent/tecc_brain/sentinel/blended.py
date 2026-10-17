"""Agent 1 — Upgraded News & NLP Risk Sentinel.

Fixes the naive "vice-versa" trap via two specialized pipelines:
1. Pipeline 1: Upgraded Market Statement (Macro Regime Score M in [0, 1]):
   - CMC Fear & Greed with Sigmoid Tail Amplification + Velocity Boost (35%)
   - Grok Structured X-Pulse Capitulation vs Euphoria (35%)
   - CoinGlass Macro Flush Confirmation: 24h Long Liq Ratio + BTC Funding (30%)
   Formula: M = 0.35 * CMC + 0.35 * Grok_Macro + 0.30 * CoinGlass_Macro

2. Pipeline 2: Upgraded Token Check (FinBERT + Grok + CoinGlass):
   - GATE 0: Hard Circuit Breaker (Adverse Selection Veto Gate I_Safe in {0, 1})
     If structural exploit/insolvency/de-peg detected with P(negative) > 0.85 -> I_Safe = 0 -> S_Token = 0.0 (Immediate Sell)
   - If I_Safe = 1 (Fundamentals Safe):
     S_Token = I_Safe * (0.45 * C_CoinGlass + 0.30 * F_FinBERT + 0.25 * G_Grok)
     Where:
     - Pillar A: CoinGlass Token Microstructure (OI vs Price, Funding Squeeze, Whale vs Retail, Spot vs Perp CVD) (45%)
     - Pillar B: Stateful FinBERT with Exponential Time-Decay (w_i = exp(-lambda * delta_t_hours)) (30%)
     - Pillar C: Grok Dual-Persona Token Check (Retail Contrarian + Security Tracker) (25%)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from tecc_brain.intent.firewall import scan
from tecc_brain.models import MarketSnapshot, NewsSignal
from tecc_brain.reference import Reference
from tecc_brain.sentinel import (
    INSOLVENCY_TRIGGERS,
    HeadlineSignal,
    compute_time_decayed_finbert_score,
)
from tecc_brain.sentinel.cmc_feargreed import CmcFearGreedClient, FearGreedReading
from tecc_brain.sentinel.coinglass import CoinGlassClient, CoinGlassMacroMetrics, CoinGlassTokenReport
from tecc_brain.sentinel.grok import GrokMacroRubric, GrokSentinel, GrokTokenRubric

# Pipeline 1 Weights
CMC_MACRO_WEIGHT = 0.35
GROK_MACRO_WEIGHT = 0.35
COINGLASS_MACRO_WEIGHT = 0.30

# Pipeline 2 Weights
COINGLASS_TOKEN_WEIGHT = 0.30
FINBERT_TOKEN_WEIGHT = 0.50
GROK_TOKEN_WEIGHT = 0.20

RegimeLabel = Literal["NORMAL_MARKET", "TEMPORARY_LIQUIDITY_DISTRESS", "FUNDAMENTAL_PEG_FAILURE"]
REGIME_LABEL_MAP: dict[str, RegimeLabel] = {
    "normal": "NORMAL_MARKET",
    "distress": "TEMPORARY_LIQUIDITY_DISTRESS",
    "failure": "FUNDAMENTAL_PEG_FAILURE",
}


# How the token check becomes the P(negative) that feeds the regime model (review Finding D, backtested on the
# USDC-SVB, stETH-Celsius and UST episodes — see strategy/sentinel_backtest.py):
#   "anchored" (default): FinBERT's news P(negative) is the level; CoinGlass and Grok only move it when they deviate
#                         from neutral (0.5): p = (1 − F) − w_C·(C − 0.5) − w_G·(G − 0.5).
#   "linear"  (original): p = 1 − (w_C·C + w_F·F + w_G·G). With neutral C and G this reads "no signal" as ~50% bad
#                         news, adding about +0.28 to P(negative) on calm days and costing the Brain its autonomy.
# Weights 0.30 / 0.50 / 0.20 (was 0.45 / 0.30 / 0.25): the backtest cannot validate CoinGlass or Grok (no history),
# so together they may move P(negative) by at most ±0.25 around FinBERT's reading.
TOKEN_P_NEGATIVE_MODE = "anchored"


def token_p_negative(cg_score: float, finbert_score: float, grok_score: float) -> float:
    if TOKEN_P_NEGATIVE_MODE == "linear":
        p = 1.0 - (COINGLASS_TOKEN_WEIGHT * cg_score + FINBERT_TOKEN_WEIGHT * finbert_score + GROK_TOKEN_WEIGHT * grok_score)
    else:
        p = (1.0 - finbert_score) - COINGLASS_TOKEN_WEIGHT * (cg_score - 0.5) - GROK_TOKEN_WEIGHT * (grok_score - 0.5)
    return round(min(1.0, max(0.0, p)), 3)


class MarketStatementReport(BaseModel):
    cmc_score: float = Field(ge=0, le=1, description="Contrarian CMC F&G with Sigmoid tail amplification (35%)")
    grok_score: float = Field(ge=0, le=1, description="Grok structured X-pulse capitulation vs euphoria (35%)")
    coinglass_score: float = Field(ge=0, le=1, default=0.5, description="CoinGlass 24h global liquidation & funding flush (30%)")
    market_buy_sell_score: float = Field(ge=0, le=1, description="Macro Regime Score M in [0, 1]")
    cmc_delta: int = Field(default=0, description="24h CMC Fear & Greed change")
    grok_rubric: dict[str, int] = Field(default_factory=dict)
    coinglass_flush: dict[str, float] = Field(default_factory=dict)


class TokenCheckReport(BaseModel):
    symbol: str
    gate_safe: int = Field(ge=0, le=1, default=1, description="Adverse Selection Veto Gate I_Safe (1 = Safe, 0 = Vetoed)")
    coinglass_score: float = Field(ge=0, le=1, default=0.5, description="CoinGlass token microstructure score C_CoinGlass (45%)")
    finbert_score: float = Field(ge=0, le=1, default=0.5, description="Stateful time-decayed FinBERT score F_FinBERT (30%)")
    grok_score: float = Field(ge=0, le=1, default=0.5, description="Grok dual-persona token score G_Grok (25%)")
    token_buy_sell_score: float = Field(ge=0, le=1, description="Final Token Score S_Token in [0, 1]")
    veto_reason: str = Field(default="", description="Reason for veto if I_Safe == 0")
    details: dict[str, Any] = Field(default_factory=dict)


class AssetSentiment(BaseModel):
    symbol: str
    p_negative: float = Field(ge=0, le=1)
    buy_sell_score: float = Field(ge=0, le=1, description="0 strong sell .. 1 strong buy, blended")
    token_check: TokenCheckReport | None = None


class BlendedSentinelReport(BaseModel):
    fear_greed: FearGreedReading
    market_statement: MarketStatementReport
    assets: dict[str, AssetSentiment]
    overall_buy_sell_score: float = Field(ge=0, le=1, description="Macro Regime Score M in [0, 1]")


def blend(fear_greed_score: float, asset_p_negative: float) -> float:
    """Convenience helper for baseline 50/50 blend."""
    asset_buy_sell = 1.0 - asset_p_negative
    return 0.5 * fear_greed_score + 0.5 * asset_buy_sell


class NewsRiskSentinel:
    """Agent 1 — Upgraded News & NLP Risk Sentinel.

    Executes Pipeline 1 (Macro Regime Score M) and Pipeline 2 (Token Check with GATE 0 Veto).
    """

    def __init__(
        self,
        fear_greed: CmcFearGreedClient | None = None,
        grok: GrokSentinel | None = None,
        coinglass: CoinGlassClient | None = None,
        ref: Reference | None = None,
    ) -> None:
        self.fear_greed = fear_greed or CmcFearGreedClient()
        self.coinglass = coinglass or CoinGlassClient()
        self._grok = grok
        self._ref = ref

    def _grok_for(self, ref: Reference) -> GrokSentinel:
        if self._grok is None or self._ref is not ref:
            self._grok, self._ref = GrokSentinel(ref), ref
        return self._grok

    def assess(self, snapshot: MarketSnapshot, ref: Reference) -> BlendedSentinelReport:
        fg = self.fear_greed.fetch()
        grok = self._grok_for(ref)
        finbert = grok.fallback

        # =====================================================================
        # Pipeline 1: Upgraded Market Statement (Macro Regime Score M in [0, 1])
        # 1. CMC Fear & Greed with Sigmoid Tail Amplification (35%)
        # 2. Grok X-Pulse Structured Capitulation vs Euphoria (35%)
        # 3. CoinGlass Macro Flush Confirmation (30%)
        # =====================================================================
        cmc_score = fg.amplified_buy_sell_score
        grok_macro_rubric = grok.macro_rubric()
        grok_macro_score = grok_macro_rubric.macro_score
        cg_macro_metrics = self.coinglass.macro_flush()
        cg_macro_score = cg_macro_metrics.macro_score

        market_score = round(
            CMC_MACRO_WEIGHT * cmc_score
            + GROK_MACRO_WEIGHT * grok_macro_score
            + COINGLASS_MACRO_WEIGHT * cg_macro_score,
            3,
        )

        market_report = MarketStatementReport(
            cmc_score=round(cmc_score, 3),
            grok_score=round(grok_macro_score, 3),
            coinglass_score=round(cg_macro_score, 3),
            market_buy_sell_score=market_score,
            cmc_delta=fg.delta_24h,
            grok_rubric={
                "retail_capitulation_index": grok_macro_rubric.retail_capitulation_index,
                "retail_euphoria_index": grok_macro_rubric.retail_euphoria_index,
            },
            coinglass_flush={
                "long_liq_ratio_24h": cg_macro_metrics.long_liq_ratio_24h,
                "short_liq_ratio_24h": cg_macro_metrics.short_liq_ratio_24h,
                "btc_funding_rate": cg_macro_metrics.btc_funding_rate,
            },
        )

        # =====================================================================
        # Pipeline 2: Upgraded Token Check (GATE 0 + 3 Pillars)
        # =====================================================================
        recent_by_symbol: dict[str, list[str]] = {}
        for n in snapshot.news:
            verdict = scan(n.headline)
            if not any(t.value != "DRAIN" for t in verdict.threats):
                recent_by_symbol.setdefault(n.entity, []).append(verdict.normalized)

        assets: dict[str, AssetSentiment] = {}
        for symbol in snapshot.pegs:
            headlines = recent_by_symbol.get(symbol, [])

            # Pillar B: Stateful FinBERT Sentinel with Exponential Time-Decay + Veto Gate
            finbert_signals: list[HeadlineSignal] = []
            for n in snapshot.news:
                if n.entity != symbol:
                    continue
                verdict = scan(n.headline)
                if any(t.value != "DRAIN" for t in verdict.threats):
                    continue
                sig = finbert.score(verdict.normalized, timestamp=snapshot.as_of)
                if sig:
                    if n.p_negative > sig.p_negative:
                        sig = sig.model_copy(update={"p_negative": n.p_negative})
                    finbert_signals.append(sig)
                else:
                    lower = verdict.normalized.lower()
                    is_trig = any(t in lower for t in INSOLVENCY_TRIGGERS)
                    finbert_signals.append(
                        HeadlineSignal(
                            symbol=symbol,
                            entity=symbol,
                            p_negative=n.p_negative,
                            headline=verdict.normalized,
                            matched_terms=[],
                            source=n.source,
                            is_insolvency_trigger=bool(is_trig and n.p_negative >= 0.70),
                            timestamp=snapshot.as_of,
                        )
                    )

            finbert_score, finbert_veto, finbert_veto_reason = compute_time_decayed_finbert_score(
                finbert_signals, now=snapshot.as_of
            )

            # Pillar C: Grok API Dual-Persona Token Check
            grok_token = grok.token_rubric(symbol, headlines)
            grok_score = grok_token.token_score
            grok_veto = grok_token.security_alert_detected
            grok_veto_reason = grok_token.security_details

            # Pillar A: CoinGlass Token Derivatives Microstructure
            cg_token = self.coinglass.token_microstructure(symbol)
            cg_score = cg_token.composite_score

            # GATE 0: Hard Circuit Breaker (Adverse Selection Veto Gate)
            if finbert_veto:
                gate_safe = 0
                veto_reason = finbert_veto_reason
            elif grok_veto:
                gate_safe = 0
                veto_reason = f"Grok Security Alert Veto: {grok_veto_reason}"
            else:
                gate_safe = 1
                veto_reason = ""

            # S_Token = I_Safe * (0.45 * C_CoinGlass + 0.30 * F_FinBERT + 0.25 * G_Grok)
            if gate_safe == 0:
                token_score = 0.0
                combined_score = 0.0
                p_negative = 1.0  # Maximum negative sentiment trips circuit breaker
            else:
                raw_token_score = (
                    COINGLASS_TOKEN_WEIGHT * cg_score
                    + FINBERT_TOKEN_WEIGHT * finbert_score
                    + GROK_TOKEN_WEIGHT * grok_score
                )
                token_score = round(raw_token_score, 3)
                combined_score = round(0.50 * market_score + 0.50 * token_score, 3)
                p_negative = token_p_negative(cg_score, finbert_score, grok_score)

            token_report = TokenCheckReport(
                symbol=symbol,
                gate_safe=gate_safe,
                coinglass_score=cg_score,
                finbert_score=finbert_score,
                grok_score=grok_score,
                token_buy_sell_score=token_score,
                veto_reason=veto_reason,
                details={
                    "coinglass_metrics": cg_token.details,
                    "grok_details": {
                        "retail_panic": grok_token.retail_panic_index,
                        "retail_fomo": grok_token.retail_fomo_index,
                        "security_alert": grok_token.security_alert_detected,
                    },
                },
            )

            assets[symbol] = AssetSentiment(
                symbol=symbol,
                p_negative=p_negative,
                buy_sell_score=combined_score,
                token_check=token_report,
            )

        return BlendedSentinelReport(
            fear_greed=fg,
            market_statement=market_report,
            assets=assets,
            overall_buy_sell_score=market_score,
        )

    def _apply(self, snapshot: MarketSnapshot, ref: Reference) -> MarketSnapshot:
        """Raises (never lowers) each tracked peg's sentiment_negative to match the blend, and logs one
        audit-trail NewsSignal per asset so the nlp_sentinel agent report shows it. Called via `make_news_hook`.
        """
        report = self.assess(snapshot, ref)
        pegs = dict(snapshot.pegs)
        news = list(snapshot.news)
        for symbol, a in report.assets.items():
            peg = pegs.get(symbol)
            if peg is None:
                continue
            pegs[symbol] = peg.model_copy(update={"sentiment_negative": max(peg.sentiment_negative, a.p_negative)})

            tc = a.token_check
            if tc and tc.gate_safe == 0:
                news.append(
                    NewsSignal(
                        entity=symbol,
                        p_negative=a.p_negative,
                        headline=f"🚨 VETO CIRCUIT BREAKER on {symbol}: {tc.veto_reason}. Forced Token Score 0.00.",
                        source="GATE 0 Hard Circuit Breaker (FinBERT/Grok Veto)",
                    )
                )
            else:
                news.append(
                    NewsSignal(
                        entity=symbol,
                        p_negative=a.p_negative,
                        headline=(
                            f"Upgraded Sentinel: Macro {report.overall_buy_sell_score:.2f} (35% CMC + 35% Grok + 30% CoinGlass) | "
                            f"Token {tc.token_buy_sell_score if tc else 0.5:.2f} (30% CoinGlass + 50% FinBERT + 20% Grok) "
                            f"→ buy/sell {a.buy_sell_score:.2f}."
                        ),
                        source="Upgraded Market Statement & Token Check (FinBERT + Grok + CoinGlass)",
                    )
                )
        return snapshot.model_copy(update={"pegs": pegs, "news": news})


def make_news_hook(sentinel: NewsRiskSentinel, ref: Reference) -> Callable[[MarketSnapshot], MarketSnapshot]:
    """The function to actually pass as `BrainDeps(news_hook=...)` — binds `ref` once, cleanly, no self-hack."""
    def _hook(snapshot: MarketSnapshot) -> MarketSnapshot:
        return sentinel._apply(snapshot, ref)
    return _hook


__all__ = [
    "TOKEN_P_NEGATIVE_MODE",
    "token_p_negative",
    "CMC_MACRO_WEIGHT",
    "COINGLASS_MACRO_WEIGHT",
    "COINGLASS_TOKEN_WEIGHT",
    "FINBERT_TOKEN_WEIGHT",
    "GROK_MACRO_WEIGHT",
    "GROK_TOKEN_WEIGHT",
    "AssetSentiment",
    "BlendedSentinelReport",
    "MarketStatementReport",
    "NewsRiskSentinel",
    "REGIME_LABEL_MAP",
    "RegimeLabel",
    "TokenCheckReport",
    "blend",
    "make_news_hook",
]

"""Agent 1 — News & NLP Risk Sentinel: 50% CMC Fear & Greed (market-wide) + 50% Grok/FinBERT asset sentiment,
feeding the EXISTING 3-regime classifier in risk/regime.py rather than duplicating it.

Why feed sentiment_negative instead of adding a parallel classifier: risk/regime.py's logit model already
combines sentiment with price gap, redemption status, reserve quality and contagion, validated against real
episodes (USDC-SVB, stETH-Celsius, UST). A second, independent classifier would let this agent override that
work instead of informing it — exactly the sentiment-only-veto failure mode BRAIN_DESIGN §2.1 warns against.
So this module computes one number per asset (p_negative, 0..1) from the blend and raises (never lowers)
PegState.sentiment_negative with it, the same mechanism `sentinel/__init__.py::apply_signal` already uses for
headline-driven updates — the regime model does the rest.

The three regime labels in the task spec map 1:1 onto the existing `Regime` literal:
    NORMAL_MARKET                 <- "normal"
    TEMPORARY_LIQUIDITY_DISTRESS  <- "distress"
    FUNDAMENTAL_PEG_FAILURE       <- "failure"
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field

from tecc_brain.models import MarketSnapshot, NewsSignal
from tecc_brain.reference import Reference
from tecc_brain.sentinel.cmc_feargreed import CmcFearGreedClient, FearGreedReading
from tecc_brain.sentinel.grok import GrokSentinel

FEAR_GREED_WEIGHT = 0.5
ASSET_SENTIMENT_WEIGHT = 0.5
RegimeLabel = Literal["NORMAL_MARKET", "TEMPORARY_LIQUIDITY_DISTRESS", "FUNDAMENTAL_PEG_FAILURE"]
REGIME_LABEL_MAP: dict[str, RegimeLabel] = {
    "normal": "NORMAL_MARKET", "distress": "TEMPORARY_LIQUIDITY_DISTRESS", "failure": "FUNDAMENTAL_PEG_FAILURE",
}


class MarketStatementReport(BaseModel):
    cmc_score: float = Field(ge=0, le=1, description="Contrarian CMC Fear & Greed score (0 sell .. 1 buy)")
    grok_score: float = Field(ge=0, le=1, description="Contrarian Grok crowd statement score (0 sell .. 1 buy)")
    market_buy_sell_score: float = Field(ge=0, le=1, description="50/50 blend of CMC and Grok market statements")


class TokenCheckReport(BaseModel):
    symbol: str
    grok_score: float = Field(ge=0, le=1, description="Grok asset-specific sentiment score (0 sell .. 1 buy)")
    finbert_score: float = Field(ge=0, le=1, description="FinBERT 7-day headline inference score (0 sell .. 1 buy)")
    token_buy_sell_score: float = Field(ge=0, le=1, description="50/50 blend of Grok and FinBERT token check")


class AssetSentiment(BaseModel):
    symbol: str
    p_negative: float = Field(ge=0, le=1)
    buy_sell_score: float = Field(ge=0, le=1, description="0 strong sell .. 1 strong buy, blended")
    token_check: TokenCheckReport | None = None


class BlendedSentinelReport(BaseModel):
    fear_greed: FearGreedReading
    market_statement: MarketStatementReport
    assets: dict[str, AssetSentiment]
    overall_buy_sell_score: float = Field(ge=0, le=1, description="50/50 market statement score")


def blend(fear_greed_score: float, asset_p_negative: float) -> float:
    """(0..1 buy/sell) for one asset: 50% market-wide score + 50% (1 − asset-specific P(negative))."""
    asset_buy_sell = 1.0 - asset_p_negative
    return FEAR_GREED_WEIGHT * fear_greed_score + ASSET_SENTIMENT_WEIGHT * asset_buy_sell


class NewsRiskSentinel:
    """Agent 1. Call `.assess(snapshot, ref)` each cycle (propose, or the hourly monitor); pass
    `make_news_hook(sentinel, ref)` into `BrainDeps(news_hook=...)` so the blend reaches the regime
    classifier exactly like a headline would.
    """

    def __init__(
        self, fear_greed: CmcFearGreedClient | None = None, grok: GrokSentinel | None = None, ref: Reference | None = None
    ) -> None:
        self.fear_greed = fear_greed or CmcFearGreedClient()
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

        # Formula 1: Market Statement (50% CMC Fear & Greed + 50% Grok Macro Sentiment)
        cmc_score = fg.buy_sell_score
        grok_market_score = grok.market_sentiment()
        market_score = 0.5 * cmc_score + 0.5 * grok_market_score
        market_report = MarketStatementReport(
            cmc_score=round(cmc_score, 3),
            grok_score=round(grok_market_score, 3),
            market_buy_sell_score=round(market_score, 3),
        )

        # Formula 2: Token Check per asset (50% Grok Asset + 50% FinBERT Asset)
        recent_by_symbol: dict[str, list[str]] = {}
        for n in snapshot.news:
            recent_by_symbol.setdefault(n.entity, []).append(n.headline)

        assets: dict[str, AssetSentiment] = {}
        for symbol in snapshot.pegs:
            headlines = recent_by_symbol.get(symbol, [])
            # Grok asset reading
            grok_p_neg = grok.asset_sentiment(symbol, headlines)
            grok_asset_score = 1.0 - grok_p_neg

            # FinBERT asset reading over headlines
            finbert_p_negs = []
            for h in headlines:
                sig = finbert.score(h)
                if sig:
                    finbert_p_negs.append(sig.p_negative)
            finbert_p_neg = max(finbert_p_negs) if finbert_p_negs else 0.05
            finbert_asset_score = 1.0 - finbert_p_neg

            # 50/50 Token Check formula
            token_score = 0.5 * grok_asset_score + 0.5 * finbert_asset_score
            token_report = TokenCheckReport(
                symbol=symbol,
                grok_score=round(grok_asset_score, 3),
                finbert_score=round(finbert_asset_score, 3),
                token_buy_sell_score=round(token_score, 3),
            )

            # Combined overall buy/sell score (market statement + token check)
            combined_score = 0.5 * market_score + 0.5 * token_score
            p_negative = round(1.0 - token_score, 3)

            assets[symbol] = AssetSentiment(
                symbol=symbol,
                p_negative=p_negative,
                buy_sell_score=round(combined_score, 3),
                token_check=token_report,
            )

        return BlendedSentinelReport(
            fear_greed=fg,
            market_statement=market_report,
            assets=assets,
            overall_buy_sell_score=round(market_score, 3),
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
            news.append(NewsSignal(
                entity=symbol, p_negative=a.p_negative,
                headline=f"Blended sentinel: Market Statement {report.overall_buy_sell_score:.2f} (50% CMC F&G + 50% Grok Macro) "
                         f"+ Token Check {a.token_check.token_buy_sell_score if a.token_check else 0.5:.2f} (50% Grok + 50% FinBERT) "
                         f"→ buy/sell {a.buy_sell_score:.2f}.",
                source="blended (Two 50/50 Formulas: Market & Token Check)",
            ))
        return snapshot.model_copy(update={"pegs": pegs, "news": news})


def make_news_hook(sentinel: NewsRiskSentinel, ref: Reference) -> Callable[[MarketSnapshot], MarketSnapshot]:
    """The function to actually pass as `BrainDeps(news_hook=...)` — binds `ref` once, cleanly, no self-hack."""
    def _hook(snapshot: MarketSnapshot) -> MarketSnapshot:
        return sentinel._apply(snapshot, ref)
    return _hook


__all__ = [
    "ASSET_SENTIMENT_WEIGHT",
    "AssetSentiment",
    "BlendedSentinelReport",
    "FEAR_GREED_WEIGHT",
    "MarketStatementReport",
    "NewsRiskSentinel",
    "REGIME_LABEL_MAP",
    "RegimeLabel",
    "TokenCheckReport",
    "blend",
    "make_news_hook",
]

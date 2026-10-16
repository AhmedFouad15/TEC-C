"""NLP Risk Sentinel inputs. Member 4's FinBERT is the real scorer; `LexiconSentinel` is the offline fallback so the
demo (Scene 2: type a headline, watch the regimes move) works without a model server.

Headlines only ever change *sentiment*, one of five regime inputs. Words alone cannot push a peg into "failure":
that needs price, redemption, reserve or liquidity evidence too (mentor's point; Vault Sovereignty).
"""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import BaseModel, Field

from tecc_brain.intent.firewall import scan
from tecc_brain.models import MarketSnapshot, NewsSignal
from tecc_brain.reference import Reference

MAX_HEADLINE = 500
BASE_NEGATIVE = 0.05
FLOOR, CEILING = 0.02, 0.98

ENTITY_ALIASES: dict[str, tuple[str, ...]] = {
    "USDC": ("usdc", "circle", "usd coin"),
    "USDT": ("usdt", "tether"),
    "XAUT": ("xaut", "tether gold"),
    "DAI": ("dai", "makerdao", "maker"),
    "FDUSD": ("fdusd", "first digital"),
    "UST": ("ust", "terrausd", "terra", "luna"),
    "stETH": ("steth", "lido"),
    "rETH": ("reth", "rocket pool"),
    "ezETH": ("ezeth", "renzo"),
    "PAXG": ("paxg", "paxos", "pax gold"),
}
# (pattern, weight): weights add to BASE_NEGATIVE, then clamp. Auditable on purpose.
LEXICON: tuple[tuple[str, float], ...] = (
    (r"death spiral", 0.45),
    (r"collaps\w*|insolven\w*|bankrupt\w*|fraud\w*|exploit\w*|hack(?:ed|s)?|de-?peg\w*|run on", 0.35),
    (r"halt\w*|paus\w*|frozen|freez\w*|suspend\w*", 0.30),
    (r"stuck|fail(?:ed|s|ure)?|loss(?:es)?|lawsuit|investigat\w*|outflows?|plung\w*|crash\w*|"
     r"fall(?:s|ing)?|drops?|fears?|concerns?|warn\w*|downgrad\w*|exposure", 0.20),
    (r"backstop\w*|guarante\w*|fully (?:backed|covered)|covered|restor\w*|recover\w*|re-?peg\w*|made whole|reassur\w*", -0.25),
    (r"grows?|expands?|record (?:high|inflows)|approv\w*", -0.05),
)
_LEXICON = tuple((re.compile(rf"\b(?:{p})\b"), w) for p, w in LEXICON)


class HeadlineSignal(BaseModel):
    symbol: str
    entity: str = Field(description="The name that matched in the headline")
    p_negative: float = Field(ge=0, le=1)
    headline: str
    matched_terms: list[str]
    source: str = "offline lexicon (FinBERT fallback)"


class SentinelSource(Protocol):
    """Member 4's FinBERT service implements this (Phase 8 adapter)."""

    def score(self, headline: str) -> HeadlineSignal | None: ...


class LexiconSentinel:
    def __init__(self, ref: Reference) -> None:
        self.aliases = {s: names for s, names in ENTITY_ALIASES.items() if s in ref.assets}

    def _entity(self, lower: str) -> tuple[str, str] | None:
        best: tuple[int, int, str, str] | None = None
        for symbol, names in self.aliases.items():
            for name in names:
                m = re.search(rf"\b{re.escape(name)}\b", lower)
                if m and (best is None or (m.start(), -len(name)) < (best[0], best[1])):
                    best = (m.start(), -len(name), symbol, name)
        return (best[2], best[3]) if best else None

    def score(self, headline: str) -> HeadlineSignal | None:
        if not headline.strip() or len(headline) > MAX_HEADLINE:
            return None
        verdict = scan(headline)
        if not verdict.allowed:
            return None  # a "headline" that carries instructions is not news
        lower = verdict.normalized.lower()
        entity = self._entity(lower)
        if entity is None:
            return None
        terms: list[str] = []
        p = BASE_NEGATIVE
        for pattern, weight in _LEXICON:
            for m in pattern.finditer(lower):
                terms.append(m.group(0))
                p += weight
        return HeadlineSignal(
            symbol=entity[0], entity=entity[1], p_negative=round(min(CEILING, max(FLOOR, p)), 3),
            headline=verdict.normalized, matched_terms=terms,
        )


def apply_signal(snapshot: MarketSnapshot, signal: HeadlineSignal) -> MarketSnapshot:
    """A new snapshot with the headline in the news and the asset's sentiment raised (never lowered) to match."""
    pegs = dict(snapshot.pegs)
    peg = pegs.get(signal.symbol)
    if peg is not None:
        pegs[signal.symbol] = peg.model_copy(update={"sentiment_negative": max(peg.sentiment_negative, signal.p_negative)})
    news = [*snapshot.news, NewsSignal(entity=signal.symbol, p_negative=signal.p_negative, headline=signal.headline,
                                       source=signal.source)]
    return snapshot.model_copy(update={"pegs": pegs, "news": news})


__all__ = ["ENTITY_ALIASES", "HeadlineSignal", "LexiconSentinel", "SentinelSource", "apply_signal"]

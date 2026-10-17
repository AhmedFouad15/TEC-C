"""CoinMarketCap Fear & Greed index — the market-wide half of the NLP Risk Sentinel's 50/50 blend
(BRAIN_DESIGN extension: Agent 1, team notes). Never raises into the pipeline: a failed fetch degrades to a
neutral reading rather than blocking a mandate, because the hard filters and vault radius are the real backstop,
not this feed (see risk/filters.py's docstring: "sentiment alone never vetoes").
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel, Field

CMC_FEAR_GREED_URL = "https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest"
NEUTRAL_VALUE = 50
DEFAULT_TIMEOUT_S = 5.0


class FearGreedReading(BaseModel):
    value: int = Field(ge=0, le=100, description="0 = extreme fear, 100 = extreme greed")
    classification: str
    as_of: datetime
    source: str = "cmc_fear_greed"
    prev_value: int | None = Field(default=None, description="Previous 24h reading for velocity calculation")
    delta_24h: int = Field(default=0, description="Change vs yesterday: value - prev_value")

    @property
    def buy_sell_score(self) -> float:
        """0 (strong sell) .. 1 (strong buy) — contrarian ("vice versa") scale per project spec:
        high greed (value -> 100) => motivated to sell (score -> 0.0)
        high fear / depressed (value -> 0) => motivated to buy (score -> 1.0)
        neutral (value = 50) => 0.5
        """
        return (100.0 - float(self.value)) / 100.0

    @property
    def amplified_buy_sell_score(self) -> float:
        """Contrarian score with Sigmoid Tail Amplification and Velocity Boost.

        - 40..60 is noise -> compressed towards 0.50.
        - Extremes (<20 Extreme Fear or >80 Extreme Greed) amplified towards 1.0 or 0.0.
        - Velocity Boost (ΔFG): If Fear was extreme and turns up (e.g. 12 -> 16, panic exhausting),
          adds +0.10 reversal boost.
        """
        f_inv = (100.0 - float(self.value)) / 100.0

        # Sigmoid Tail Amplification: suppress noise around 40-60, amplify extremes
        if 40 <= self.value <= 60:
            score = 0.50 + (f_inv - 0.50) * 0.40
        elif self.value < 20:
            score = min(1.0, f_inv + 0.08)
        elif self.value > 80:
            score = max(0.0, f_inv - 0.08)
        else:
            score = f_inv

        # Velocity Boost (ΔFG): if fear was extreme and turns up (panic exhausting)
        effective_delta = self.delta_24h if self.delta_24h != 0 else ((self.value - self.prev_value) if self.prev_value is not None else 0)
        if self.value <= 30 and effective_delta > 0:
            score = min(1.0, score + 0.10)

        return round(max(0.0, min(1.0, score)), 3)


def _neutral(source: str = "cmc_fear_greed (fallback: unavailable)") -> FearGreedReading:
    return FearGreedReading(value=NEUTRAL_VALUE, classification="Neutral", as_of=datetime.now(timezone.utc), source=source)


class CmcFearGreedClient:
    """Thin client for CMC's Fear & Greed endpoint. Requires CMC_API_KEY; degrades to neutral without it."""

    def __init__(self, api_key: str | None = None, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("CMC_API_KEY")
        self.timeout_s = timeout_s

    def fetch(self) -> FearGreedReading:
        if not self.api_key:
            return _neutral("cmc_fear_greed (fallback: CMC_API_KEY not set)")
        try:
            resp = httpx.get(
                CMC_FEAR_GREED_URL,
                headers={"X-CMC_PRO_API_KEY": self.api_key, "Accept": "application/json"},
                timeout=self.timeout_s,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            return FearGreedReading(
                value=int(data["value"]), classification=str(data.get("value_classification", "Unknown")),
                as_of=datetime.now(timezone.utc),
            )
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            return _neutral("cmc_fear_greed (fallback: fetch failed)")


__all__ = ["CmcFearGreedClient", "FearGreedReading", "NEUTRAL_VALUE"]

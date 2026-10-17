"""Backtest the News Risk Sentinel's weights on the three historical de-pegs (review Finding D).

Every day of every episode is fed through the *real* `NewsRiskSentinel.assess` (same code as production) with:
* that day's Fear & Greed value and headline (backtests.json, approximate, hand-set),
* the FinBERT-equivalent P(negative) of the day (the episode's `sentiment_negative`),
* CoinGlass and Grok in their offline mode (no historical data exists for them; this is what the demo runs too).
The sentinel's P(negative) then raises the day's sentiment input to the regime model — exactly what the live news
hook does — and the Brain's strategy is replayed. The score of a weighting is the Brain's P&L per episode.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from tecc_brain.models import MarketSnapshot, NewsSignal, PegState
from tecc_brain.reference import Reference, load_reference, read_data_json
from tecc_brain.sentinel import blended
from tecc_brain.sentinel.cmc_feargreed import FearGreedReading
from tecc_brain.sentinel.coinglass import CoinGlassClient
from tecc_brain.sentinel.grok import GrokSentinel
from tecc_brain.strategy.backtest import available_backtests, run_backtest

Weights = tuple[float, float, float]  # (CoinGlass, FinBERT, Grok) token weights, summing to 1
CURRENT: Weights = (blended.COINGLASS_TOKEN_WEIGHT, blended.FINBERT_TOKEN_WEIGHT, blended.GROK_TOKEN_WEIGHT)


class _StaticFearGreed:
    """Replays one historical Fear & Greed reading (with yesterday's, for the velocity boost)."""

    def __init__(self, value: int, prev: int | None, as_of: datetime) -> None:
        self.value, self.prev, self.as_of = value, prev, as_of

    def fetch(self) -> FearGreedReading:
        label = "Extreme Fear" if self.value < 25 else "Fear" if self.value < 45 else "Neutral" if self.value <= 55 else "Greed"
        delta = self.value - self.prev if self.prev is not None else 0
        return FearGreedReading(value=self.value, classification=label, as_of=self.as_of, prev_value=self.prev, delta_24h=delta)


@contextmanager
def token_weights(w: Weights, mode: str | None = None) -> Iterator[None]:
    saved = (blended.COINGLASS_TOKEN_WEIGHT, blended.FINBERT_TOKEN_WEIGHT, blended.GROK_TOKEN_WEIGHT,
             blended.TOKEN_P_NEGATIVE_MODE)
    blended.COINGLASS_TOKEN_WEIGHT, blended.FINBERT_TOKEN_WEIGHT, blended.GROK_TOKEN_WEIGHT = w
    blended.TOKEN_P_NEGATIVE_MODE = mode or saved[3]
    try:
        yield
    finally:
        (blended.COINGLASS_TOKEN_WEIGHT, blended.FINBERT_TOKEN_WEIGHT, blended.GROK_TOKEN_WEIGHT,
         blended.TOKEN_P_NEGATIVE_MODE) = saved


def _episode_points(episode_id: str) -> list[dict[str, Any]]:
    return next(e for e in read_data_json("backtests.json")["episodes"] if e["id"] == episode_id)["points"]


def sentinel_hook(
    episode_id: str, weights: Weights, ref: Reference, mode: str | None = None
) -> Callable[[dict[str, Any], str], float]:
    points = _episode_points(episode_id)
    prev_fg = {p["date"]: (points[i - 1]["fear_greed"] if i else None) for i, p in enumerate(points)}
    hurdle = read_data_json("backtests.json")["hurdle_rate"]

    def hook(point: dict[str, Any], symbol: str) -> float:
        as_of = datetime.fromisoformat(point["date"]).replace(tzinfo=timezone.utc)
        snapshot = MarketSnapshot(
            as_of=as_of, hurdle_rate=hurdle, source=f"backtest:{episode_id}",
            pegs={symbol: PegState(symbol=symbol, price=point["price"], sentiment_negative=point["sentiment_negative"],
                                   redemption_status=point["redemption_status"],
                                   liquidity_stress=point["liquidity_stress"], coverage=point["coverage"])},
            news=[NewsSignal(entity=symbol, p_negative=point["sentiment_negative"], headline=point["headline"],
                             source="backtest")],
        )
        sentinel = blended.NewsRiskSentinel(
            fear_greed=_StaticFearGreed(point["fear_greed"], prev_fg[point["date"]], as_of),  # type: ignore[arg-type]
            coinglass=CoinGlassClient(api_key=""), grok=GrokSentinel(ref, api_key=""), ref=ref,
        )
        with token_weights(weights, mode):
            return sentinel.assess(snapshot, ref).assets[symbol].p_negative

    return hook


CALM_SENTIMENT = 0.30  # a day whose own news P(negative) is at most this counts as calm
AUTONOMY_P_NORMAL = 0.80  # the planner's AUTO_MIN_P_NORMAL
WARNING_LEVEL = 0.60


class WeightResult(BaseModel):
    weights: Weights | None  # None = no sentinel (regime model alone)
    mode: str | None
    pnl: dict[str, float]  # episode → Brain P&L (fraction)
    worst: float
    total: float
    calm_bias: float  # mean (sentinel − news) P(negative) on calm days: 0 is calibrated
    calm_autonomy: float  # share of calm days where the Brain may still act alone (P_normal ≥ 0.80)
    ust_warning: str | None  # first day the sentinel reads UST ≥ 0.60


def evaluate(
    weights: Weights | None, ref: Reference | None = None, episodes: list[str] | None = None, mode: str | None = None
) -> WeightResult:
    ref = ref or load_reference()
    episodes = episodes or available_backtests()
    pnl: dict[str, float] = {}
    bias: list[float] = []
    autonomous: list[bool] = []
    warning = None
    for ep in episodes:
        hook = sentinel_hook(ep, weights, ref, mode) if weights is not None else None
        result = run_backtest(ep, ref, sentiment_hook=hook)
        pnl[ep] = result.strategies["tec_c"].pnl_pct
        for point, step in zip(_episode_points(ep), result.steps):
            p = hook(point, result.asset) if hook else point["sentiment_negative"]
            if point["sentiment_negative"] <= CALM_SENTIMENT:
                bias.append(p - point["sentiment_negative"])
                autonomous.append(step.probs.p_normal >= AUTONOMY_P_NORMAL)
            if ep == "ust_2022" and warning is None and p >= WARNING_LEVEL:
                warning = point["date"]
    return WeightResult(
        weights=weights, mode=mode if weights is not None else None, pnl=pnl, worst=min(pnl.values()),
        total=sum(pnl.values()), calm_bias=round(sum(bias) / len(bias), 3) if bias else 0.0,
        calm_autonomy=round(sum(autonomous) / len(autonomous), 3) if autonomous else 1.0, ust_warning=warning,
    )


def simplex(step: float = 0.05) -> list[Weights]:
    n = round(1 / step)
    return [(round(a * step, 2), round(b * step, 2), round((n - a - b) * step, 2))
            for a, b in itertools.product(range(n + 1), repeat=2) if a + b <= n]


MAX_CALM_BIAS = 0.05


def rank_key(r: WeightResult) -> tuple[bool, float, float, float, float]:
    """Best first. A weighting must first be *calibrated* (calm-day bias ≤ 0.05): a sentinel that reads silence as
    bad news can win a backtest by luck (an earlier UST exit) while switching off the Brain's autonomy every calm day.
    Then: autonomy kept, worst-episode P&L (robust), calibration, total P&L."""
    return (abs(r.calm_bias) <= MAX_CALM_BIAS, r.calm_autonomy, round(r.worst, 4), -abs(r.calm_bias), round(r.total, 4))


def grid_search(
    step: float = 0.05, episodes: list[str] | None = None, ref: Reference | None = None,
    modes: tuple[str, ...] = ("linear", "anchored"),
) -> list[WeightResult]:
    ref = ref or load_reference()
    results = [evaluate(w, ref, episodes, mode) for mode in modes for w in simplex(step)]
    return sorted(results, key=rank_key, reverse=True)


__all__ = ["CURRENT", "WeightResult", "evaluate", "grid_search", "rank_key", "sentinel_hook", "simplex", "token_weights"]

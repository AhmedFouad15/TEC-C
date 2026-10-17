"""Replay historical de-pegs day by day: the Brain vs two naive rules (pitch evidence for BRAIN_DESIGN §2.4).

* tec_c          — regime model + playbook: exits on EXIT, buys the discount once when the recovery-adjusted edge ≥ 1%
* sentiment_veto — the old PegGuard rule: sell everything when P(negative news) ≥ 60%
* mean_reversion — buy the dip once when price ≤ 0.97 × peg, assuming it always comes back

All strategies start with the same position at the first day's price; extra buys use the same ticket size.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from tecc_brain.models import PegState
from tecc_brain.reference import Reference, load_reference, read_data_json
from tecc_brain.risk.regime import RegimeProbs, assess_peg
from tecc_brain.risk.score import expected_recovery_days, recovery_edge
from tecc_brain.strategy.playbook import DEFAULT_DISCOUNT_COSTS, MIN_OPPORTUNITY_EDGE, Response, respond

SENTIMENT_VETO_THRESHOLD = 0.60
MEAN_REVERSION_TRIGGER = 0.97
STRATEGIES = ("tec_c", "sentiment_veto", "mean_reversion")


class BacktestStep(BaseModel):
    date: str
    event: str
    price: float
    probs: RegimeProbs
    dominant: str
    response: Response
    edge: float | None
    actions: dict[str, str]


class StrategyResult(BaseModel):
    name: str
    invested_usd: float
    final_value_usd: float
    pnl_pct: float
    exited_at: str | None
    bought_at: str | None


class BacktestResult(BaseModel):
    episode_id: str
    title: str
    asset: str
    steps: list[BacktestStep]
    strategies: dict[str, StrategyResult]


class _Book:
    def __init__(self, ticket: float, price: float) -> None:
        self.ticket = ticket
        self.units = ticket / price
        self.cash = 0.0
        self.invested = ticket
        self.exited_at: str | None = None
        self.bought_at: str | None = None

    def sell_all(self, price: float, date: str) -> str:
        if self.units == 0:
            return "out"
        self.cash += self.units * price
        self.units = 0.0
        self.exited_at = date
        return f"sell all @ {price:.3f}"

    def buy_once(self, price: float, date: str) -> str:
        if self.bought_at or self.exited_at:
            return "hold"
        self.units += self.ticket / price
        self.invested += self.ticket
        self.bought_at = date
        return f"buy ${self.ticket:,.0f} @ {price:.3f}"


def available_backtests() -> list[str]:
    return [e["id"] for e in read_data_json("backtests.json")["episodes"]]


def run_backtest(
    episode_id: str,
    ref: Reference | None = None,
    sentiment_hook: Callable[[dict[str, Any], str], float] | None = None,
) -> BacktestResult:
    """`sentiment_hook(point, symbol)` → P(negative) from a news sentinel; like the live news hook it can only raise
    the day's sentiment input, never lower it."""
    ref = ref or load_reference()
    data = read_data_json("backtests.json")
    episode = next((e for e in data["episodes"] if e["id"] == episode_id), None)
    if episode is None:
        raise KeyError(f"Unknown backtest {episode_id!r}; available: {available_backtests()}")
    hurdle = data["hurdle_rate"]
    asset = ref.assets[episode["asset"]]
    points = episode["points"]
    ticket = float(episode["position_usd"])
    books = {name: _Book(ticket, points[0]["price"]) for name in STRATEGIES}

    steps: list[BacktestStep] = []
    for point in points:
        date, price = point["date"], point["price"]
        sentiment = point["sentiment_negative"]
        if sentiment_hook is not None:
            sentiment = max(sentiment, sentiment_hook(point, asset.symbol))
        peg = PegState(
            symbol=asset.symbol,
            price=price,
            sentiment_negative=sentiment,
            redemption_status=point["redemption_status"],
            liquidity_stress=point["liquidity_stress"],
            coverage=point["coverage"],
        )
        assessment = assess_peg(peg, asset, hurdle)
        entry = respond(asset, assessment)
        edge = None
        if assessment.discount_to_fv > 0 and assessment.probs.dominant == "distress":
            days = expected_recovery_days(peg.redemption_status)
            edge = recovery_edge(price, assessment, asset.reserve_quality, DEFAULT_DISCOUNT_COSTS, hurdle, days)

        actions = {}
        tec = books["tec_c"]
        if entry.response == Response.EXIT:
            actions["tec_c"] = tec.sell_all(price, date)
        elif edge is not None and edge >= MIN_OPPORTUNITY_EDGE:
            actions["tec_c"] = tec.buy_once(price, date)
        else:
            actions["tec_c"] = "out" if tec.exited_at else "hold"

        veto = books["sentiment_veto"]
        actions["sentiment_veto"] = (
            veto.sell_all(price, date) if point["sentiment_negative"] >= SENTIMENT_VETO_THRESHOLD
            else ("out" if veto.exited_at else "hold")
        )

        reversion = books["mean_reversion"]
        actions["mean_reversion"] = (
            reversion.buy_once(price, date) if price <= MEAN_REVERSION_TRIGGER else "hold"
        )

        steps.append(
            BacktestStep(
                date=date, event=point.get("event", ""), price=price, probs=assessment.probs,
                dominant=assessment.probs.dominant, response=entry.response, edge=edge, actions=actions,
            )
        )

    last_price = points[-1]["price"]
    strategies = {}
    for name, book in books.items():
        final = book.cash + book.units * last_price
        strategies[name] = StrategyResult(
            name=name,
            invested_usd=book.invested,
            final_value_usd=final,
            pnl_pct=final / book.invested - 1.0,
            exited_at=book.exited_at,
            bought_at=book.bought_at,
        )
    return BacktestResult(
        episode_id=episode_id, title=episode["title"], asset=asset.symbol, steps=steps, strategies=strategies
    )

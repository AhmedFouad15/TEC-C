"""The hourly monitor: wakes up, asks Agent 1 (News & NLP Risk Sentinel) for a fresh read on every tracked
asset, and — only when a read crosses a "highly negative/positive" threshold — re-invokes the full pipeline for
that account so the regime classifier, hard filters and econometric score all get a chance to react. A loud
sentinel reading never executes anything by itself; it only earns the account a fresh pipeline pass, same as
a user typing a new request. (This is the same "sentiment alone never vetoes, never auto-acts" rule as
risk/filters.py.)

Wiring: `start_scheduler(app)` is called once from `app.py`'s FastAPI lifespan. `run_once(...)` is what both
the scheduler and `POST /trigger_hourly_monitor` call, so a judge can press a button instead of waiting an hour.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from tecc_brain.learning.store import ProfileStore
from tecc_brain.market import SnapshotSource
from tecc_brain.reference import Reference, load_reference
from tecc_brain.sentinel.blended import NewsRiskSentinel, make_news_hook
from tecc_brain.strategy.market_view import assess_market

if TYPE_CHECKING:
    from fastapi import FastAPI

HIGHLY_NEGATIVE = 0.25  # blended buy/sell score at/below this => re-evaluate (bearish enough to matter)
HIGHLY_POSITIVE = 0.85  # at/above this => re-evaluate (bullish enough that a discount-buy window may be opening)
DEFAULT_INTERVAL_MINUTES = 60
MAX_EVENTS_KEPT = 200


class MonitorEvent(BaseModel):
    account: str
    symbol: str
    trigger: str  # "negative" | "positive"
    buy_sell_score: float
    regime: str
    at: datetime
    pipeline_status: str
    summary: str


class _EventLog:
    """Small in-memory ring buffer the UI can poll (GET /api/monitor/events). Not persisted: a missed poll
    after a restart just means the next hourly tick refills it — nothing here is load-bearing for execution.
    """

    def __init__(self, max_items: int = MAX_EVENTS_KEPT) -> None:
        self._items: list[MonitorEvent] = []
        self._lock = threading.Lock()
        self.max_items = max_items

    def add(self, event: MonitorEvent) -> None:
        with self._lock:
            self._items.append(event)
            if len(self._items) > self.max_items:
                self._items = self._items[-self.max_items :]

    def recent(self, limit: int = 50) -> list[MonitorEvent]:
        with self._lock:
            return list(self._items[-limit:])


_LOG = _EventLog()


def get_event_log() -> _EventLog:
    return _LOG


def run_once(accounts: list[str], *, scenario: str = "demo", ref: Reference | None = None) -> list[MonitorEvent]:
    """Agent 1's sweep for this tick. Returns the triggers it found (and re-ran the pipeline for)."""
    ref = ref or load_reference()
    sentinel = NewsRiskSentinel(ref=ref)
    store = ProfileStore()
    snapshot = SnapshotSource(scenario).snapshot()
    report = sentinel.assess(snapshot, ref)
    triggered: list[MonitorEvent] = []

    for symbol, asset_signal in report.assets.items():
        trigger = None
        if asset_signal.buy_sell_score <= HIGHLY_NEGATIVE:
            trigger = "negative"
        elif asset_signal.buy_sell_score >= HIGHLY_POSITIVE:
            trigger = "positive"
        if trigger is None:
            continue

        hooked_snapshot = make_news_hook(sentinel, ref)(snapshot)
        view = assess_market(hooked_snapshot, ref)
        regime = view.assessments[symbol].probs.dominant if symbol in view.assessments else "normal"

        for account in accounts:
            from tecc_brain.graph.pipeline import DEMO_ACCOUNT, load_or_create_profile, run_pipeline

            profile = load_or_create_profile(store, account)
            text = f"optimize yield on my {symbol}" if account == DEMO_ACCOUNT else f"review my {symbol} position"
            result = run_pipeline(
                text, account, market=SnapshotSource(scenario), store=store, ref=ref,
                news_hook=make_news_hook(sentinel, ref),
            )
            event = MonitorEvent(
                account=account, symbol=symbol, trigger=trigger, buy_sell_score=round(asset_signal.buy_sell_score, 3),
                regime=regime, at=datetime.now(timezone.utc), pipeline_status=result.status,
                summary=f"{symbol} buy/sell {asset_signal.buy_sell_score:.2f} ({trigger}), regime {regime}; "
                        f"re-run for {account} -> {result.status}"
                        + (f" ({len(result.decision.cards)} card(s))" if result.decision else "."),
            )
            _LOG.add(event)
            triggered.append(event)
    return triggered


def _tick() -> None:
    accounts = [a.strip() for a in os.environ.get("TECC_MONITOR_ACCOUNTS", "demo").split(",") if a.strip()]
    scenario = os.environ.get("TECC_MONITOR_SCENARIO", "demo")
    try:
        run_once(accounts, scenario=scenario)
    except Exception:  # noqa: BLE001 — a bad tick must never crash the scheduler thread or the API process
        import logging

        logging.getLogger("tecc_brain.monitor").exception("hourly monitor tick failed")


_scheduler = None  # module-level so start/stop are idempotent across FastAPI reload


def start_scheduler(app: "FastAPI | None" = None) -> None:
    """Call once at startup. No-op if TECC_ENABLE_HOURLY_MONITOR is unset (default off — tests and local
    `uvicorn --reload` runs should not spin up background jobs unless explicitly asked to).
    """
    global _scheduler
    if os.environ.get("TECC_ENABLE_HOURLY_MONITOR", "0") != "1" or _scheduler is not None:
        return
    from apscheduler.schedulers.background import BackgroundScheduler

    interval = int(os.environ.get("TECC_MONITOR_INTERVAL_MINUTES", DEFAULT_INTERVAL_MINUTES))
    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(_tick, "interval", minutes=interval, id="tecc_hourly_monitor", next_run_time=None)
    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


__all__ = ["MonitorEvent", "get_event_log", "run_once", "start_scheduler", "stop_scheduler"]

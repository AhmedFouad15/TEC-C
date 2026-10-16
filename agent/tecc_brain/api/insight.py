"""/api/backtest/* (pitch evidence) and /api/sentinel/headline (Scene 2: type a headline, watch the regimes move)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tecc_brain.api.deps import Scenario, get_ref
from tecc_brain.graph.pipeline import RegimeView, regime_views
from tecc_brain.market import SnapshotSource
from tecc_brain.reference import Reference
from tecc_brain.sentinel import MAX_HEADLINE, HeadlineSignal, LexiconSentinel, apply_signal
from tecc_brain.strategy.backtest import BacktestResult, available_backtests, run_backtest
from tecc_brain.strategy.market_view import assess_market

router = APIRouter(tags=["insight"])


@router.get("/api/backtest", response_model=list[str])
def backtests() -> list[str]:
    return available_backtests()


@router.post("/api/backtest/{episode}", response_model=BacktestResult)
def backtest(episode: str, ref: Reference = Depends(get_ref)) -> BacktestResult:
    if episode not in available_backtests():
        raise HTTPException(404, f"unknown episode; try one of {available_backtests()}")
    return run_backtest(episode, ref)


class HeadlineRequest(BaseModel):
    headline: str = Field(min_length=1, max_length=MAX_HEADLINE)
    scenario: Scenario = "demo"


class HeadlineResponse(BaseModel):
    signal: HeadlineSignal | None
    before: RegimeView | None
    after: RegimeView | None
    source: str
    note: str


@router.post("/api/sentinel/headline", response_model=HeadlineResponse)
def headline(req: HeadlineRequest, ref: Reference = Depends(get_ref)) -> HeadlineResponse:
    sentinel = LexiconSentinel(ref)
    signal = sentinel.score(req.headline)
    snapshot = SnapshotSource(req.scenario).snapshot()
    source = "offline lexicon (FinBERT fallback)"
    if signal is None:
        return HeadlineResponse(signal=None, before=None, after=None, source=source,
                                note="No tracked asset named, or the text carried instructions; nothing changes.")
    before = regime_views(assess_market(snapshot, ref), ref).get(signal.symbol)
    after = regime_views(assess_market(apply_signal(snapshot, signal), ref), ref).get(signal.symbol)
    return HeadlineResponse(
        signal=signal, before=before, after=after, source=source,
        note="Headlines move sentiment only; failure also needs price, redemption, reserve or liquidity evidence.",
    )

"""/api/risk/*: the Security Radar — per-asset regime probabilities, fair values and cluster stress."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tecc_brain.api.deps import Scenario, get_ref
from tecc_brain.graph.pipeline import RegimeView, regime_views
from tecc_brain.market import SnapshotSource
from tecc_brain.reference import Reference
from tecc_brain.strategy.market_view import ClusterStatus, assess_market

router = APIRouter(prefix="/api/risk", tags=["risk"])


class RegimesResponse(BaseModel):
    source: str
    as_of: datetime
    hurdle_rate: float
    regimes: dict[str, RegimeView]
    clusters: dict[str, ClusterStatus]


@router.get("/regimes", response_model=RegimesResponse)
def regimes(scenario: Scenario = "demo", ref: Reference = Depends(get_ref)) -> RegimesResponse:
    snapshot = SnapshotSource(scenario).snapshot()
    view = assess_market(snapshot, ref)
    return RegimesResponse(
        source=snapshot.source, as_of=snapshot.as_of, hurdle_rate=snapshot.hurdle_rate,
        regimes=regime_views(view, ref), clusters=view.clusters,
    )

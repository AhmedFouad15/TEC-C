"""Contagion-aware view of every pegged asset in a snapshot (BRAIN_DESIGN §2.5).

A de-peg in one asset raises the failure odds of assets that share its backing (e.g. DAI ← USDC via the PSM).
Contagion is propagated in a single step from each source's *standalone* failure probability, so a shocked
target can never feed back into its source.
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from tecc_brain.models import MarketSnapshot
from tecc_brain.reference import Reference
from tecc_brain.risk.filters import FAILURE_VETO_THRESHOLD
from tecc_brain.risk.regime import PegAssessment, assess_peg

STRESS_THRESHOLD = 0.5  # cluster is stressed when any member has p_distress + p_failure above this


class ClusterStatus(BaseModel):
    cluster: str
    members: list[str]
    stressed: bool
    failing: list[str]
    worst_member: str | None
    contagion_inputs: dict[str, float]


class MarketView(BaseModel):
    hurdle_rate: float
    assessments: dict[str, PegAssessment]
    clusters: dict[str, ClusterStatus]

    def cluster_of(self, symbol: str, ref: Reference) -> ClusterStatus | None:
        asset = ref.assets.get(symbol)
        return self.clusters.get(asset.cluster) if asset and asset.cluster else None


def assess_market(snapshot: MarketSnapshot, ref: Reference) -> MarketView:
    pegs = {sym: peg for sym, peg in snapshot.pegs.items() if sym in ref.assets}
    hurdle = snapshot.hurdle_rate

    standalone = {sym: assess_peg(peg, ref.assets[sym], hurdle) for sym, peg in pegs.items()}

    contagion: dict[str, float] = defaultdict(float)
    for link in ref.contagion:
        if link.source in standalone and link.target in pegs:
            contagion[link.target] = max(contagion[link.target], link.rho * standalone[link.source].probs.p_failure)

    assessments = {
        sym: assess_peg(peg, ref.assets[sym], hurdle, contagion=contagion[sym]) if contagion[sym] > 0 else standalone[sym]
        for sym, peg in pegs.items()
    }

    members_by_cluster: dict[str, list[str]] = defaultdict(list)
    for sym in assessments:
        cluster = ref.assets[sym].cluster
        if cluster:
            members_by_cluster[cluster].append(sym)

    clusters = {}
    for cluster, members in members_by_cluster.items():
        def stress(sym: str) -> float:
            probs = assessments[sym].probs
            return probs.p_distress + probs.p_failure

        worst = max(members, key=stress)
        clusters[cluster] = ClusterStatus(
            cluster=cluster,
            members=sorted(members),
            stressed=stress(worst) > STRESS_THRESHOLD,
            failing=sorted(m for m in members if assessments[m].probs.p_failure >= FAILURE_VETO_THRESHOLD),
            worst_member=worst,
            contagion_inputs={m: contagion[m] for m in sorted(members)},
        )

    return MarketView(hurdle_rate=hurdle, assessments=assessments, clusters=clusters)

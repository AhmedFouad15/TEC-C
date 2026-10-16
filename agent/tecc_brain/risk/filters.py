"""Hard filters (BRAIN_DESIGN §2.1): non-negotiable walls applied before scoring.

Learning and scoring only ever act inside these walls. Sentiment alone is deliberately NOT a filter: a
sentiment-only veto would have sold USDC at $0.88 in March 2023, turning a temporary mispricing into a realised
loss. Bad news feeds the regime model instead; only a likely *permanent failure* vetoes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from tecc_brain.models import RiskTier, Venue, VenueQuote
from tecc_brain.risk.regime import PegAssessment

FAILURE_VETO_THRESHOLD = 0.30
MAX_SLIPPAGE = 0.005  # 0.5 %, the pre-flight guardrail from the team spec
MIN_DEPTH_MULTIPLE = 5.0


class RejectReason(str, Enum):
    # Declaration order is the order reasons are reported in.
    HEARTBEAT_STALE = "HEARTBEAT_STALE"
    TIER_NOT_PERMITTED = "TIER_NOT_PERMITTED"
    NOT_WHITELISTED = "NOT_WHITELISTED"
    FAILURE_VETO = "FAILURE_VETO"
    NEGATIVE_EDGE = "NEGATIVE_EDGE"
    INSUFFICIENT_DEPTH = "INSUFFICIENT_DEPTH"
    SLIPPAGE_TOO_HIGH = "SLIPPAGE_TOO_HIGH"


REASON_TEXT: dict[RejectReason, str] = {
    RejectReason.HEARTBEAT_STALE: "The Brain's on-chain heartbeat is stale; it must re-sync before acting.",
    RejectReason.TIER_NOT_PERMITTED: "This protocol is riskier than your chosen risk tier allows.",
    RejectReason.NOT_WHITELISTED: "This protocol is not on your vault's approved list.",
    RejectReason.FAILURE_VETO: "An asset this position depends on is likely in permanent peg failure.",
    RejectReason.NEGATIVE_EDGE: "After recovery odds, failure loss and costs, buying this discount loses money.",
    RejectReason.INSUFFICIENT_DEPTH: "The pool is too shallow for this trade size.",
    RejectReason.SLIPPAGE_TOO_HIGH: "Estimated slippage exceeds the 0.5% pre-flight limit.",
}


@dataclass(frozen=True)
class FilterContext:
    tier: RiskTier
    whitelist: set[str] | None = None  # None = every venue approved (offline demo)
    heartbeat_alive: bool = True
    max_slippage: float = MAX_SLIPPAGE
    min_depth_multiple: float = MIN_DEPTH_MULTIPLE


def hard_filter_reasons(
    venue: Venue,
    quote: VenueQuote,
    amount_usd: float,
    assessments: Mapping[str, PegAssessment],
    ctx: FilterContext,
    *,
    edge: float | None = None,
) -> list[RejectReason]:
    """Every rule the candidate breaks, in RejectReason declaration order. Empty list = passes."""
    reasons: set[RejectReason] = set()

    if not ctx.heartbeat_alive:
        reasons.add(RejectReason.HEARTBEAT_STALE)
    if venue.tier > ctx.tier:
        reasons.add(RejectReason.TIER_NOT_PERMITTED)
    # Mirrors TetherGuardHook: a Tier 3 (unrestricted) account is not bound by the target whitelist.
    if ctx.whitelist is not None and ctx.tier < RiskTier.AGGRESSIVE and venue.id not in ctx.whitelist:
        reasons.add(RejectReason.NOT_WHITELISTED)
    if any(
        assessments[s].probs.p_failure >= FAILURE_VETO_THRESHOLD for s in venue.exposures if s in assessments
    ):
        reasons.add(RejectReason.FAILURE_VETO)
    if edge is not None and edge <= 0.0:
        reasons.add(RejectReason.NEGATIVE_EDGE)
    if amount_usd > 0:
        if quote.depth_usd < ctx.min_depth_multiple * amount_usd:
            reasons.add(RejectReason.INSUFFICIENT_DEPTH)
        estimated_slippage = venue.entry_slippage_bps / 1e4 + (amount_usd / quote.depth_usd if quote.depth_usd else 1.0)
        if estimated_slippage > ctx.max_slippage:
            reasons.add(RejectReason.SLIPPAGE_TOO_HIGH)

    return [reason for reason in RejectReason if reason in reasons]


def passes(
    venue: Venue,
    quote: VenueQuote,
    amount_usd: float,
    assessments: Mapping[str, PegAssessment],
    ctx: FilterContext,
    *,
    edge: float | None = None,
) -> bool:
    return not hard_filter_reasons(venue, quote, amount_usd, assessments, ctx, edge=edge)

"""Asset-specific response playbook (BRAIN_DESIGN §2.6) and the cards it produces.

No generic delta-neutral hedge: shorting BTC/ETH against a stablecoin adds unrelated market risk, and shorting
another stablecoin adds new counterparty risk. Each asset kind gets its own response, and temporary distress is
never sold — selling a temporary mispricing turns it into a realised loss.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from tecc_brain.models import (
    ActionType,
    Asset,
    AssetKind,
    AutonomyMode,
    Candidate,
    Card,
    CardLabel,
    MarketSnapshot,
    Portfolio,
)
from tecc_brain.reference import Reference
from tecc_brain.risk.filters import FAILURE_VETO_THRESHOLD
from tecc_brain.risk.regime import PegAssessment
from tecc_brain.risk.score import expected_recovery_days, recovery_edge
from tecc_brain.strategy.market_view import MarketView
from tecc_brain.strategy.portfolio import PortfolioRisk, position_exposures, position_expected_loss

ALGORITHMIC_HOLD_MAX_FAILURE = 0.05
DEFAULT_DISCOUNT_COSTS = 0.005  # spread + stressed slippage when buying into a de-peg
MIN_OPPORTUNITY_EDGE = 0.01  # margin of safety: the regime model is hand-calibrated, so thin edges are noise

SAFE_RAIL = "shibor_mmf"
EXIT_DESTINATION: dict[AssetKind, str] = {
    AssetKind.STABLE_FIAT: SAFE_RAIL,  # onshore money-market rail, outside the affected cluster
    AssetKind.STABLE_CRYPTO: SAFE_RAIL,
    AssetKind.STABLE_ALGORITHMIC: SAFE_RAIL,
    AssetKind.LST: "ETH",  # direct exposure to the underlying, not a short
    AssetKind.GOLD: "USDC",
}


class Response(str, Enum):
    HOLD = "HOLD"
    HOLD_NO_NEW_DEPOSITS = "HOLD_NO_NEW_DEPOSITS"
    EXIT = "EXIT"


class PlaybookEntry(BaseModel):
    symbol: str
    response: Response
    destination: str | None
    rationale: str


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def respond(asset: Asset, assessment: PegAssessment) -> PlaybookEntry:
    probs = assessment.probs
    destination = EXIT_DESTINATION.get(asset.kind, SAFE_RAIL)

    def exit_(why: str) -> PlaybookEntry:
        return PlaybookEntry(symbol=asset.symbol, response=Response.EXIT, destination=destination, rationale=why)

    if probs.p_failure >= FAILURE_VETO_THRESHOLD:
        return exit_(
            f"{asset.symbol} is likely in permanent peg failure (P={probs.p_failure:.0%}); "
            f"move to {destination}, outside the affected cluster."
        )
    if asset.kind == AssetKind.STABLE_ALGORITHMIC and not (
        probs.dominant == "normal" and probs.p_failure < ALGORITHMIC_HOLD_MAX_FAILURE
    ):
        return exit_(
            f"{asset.symbol} is algorithmic with weak reserves (q={asset.reserve_quality:.2f}); "
            "a de-peg cannot be assumed temporary."
        )
    if probs.dominant == "normal":
        return PlaybookEntry(
            symbol=asset.symbol, response=Response.HOLD, destination=None, rationale=f"{asset.symbol} is trading normally."
        )
    return PlaybookEntry(
        symbol=asset.symbol,
        response=Response.HOLD_NO_NEW_DEPOSITS,
        destination=None,
        rationale=(
            f"{asset.symbol} looks like temporary distress (P recover={probs.p_recover:.0%}): reserves and redemption "
            "mechanism still stand, so hold rather than sell at a loss; no new deposits until it normalises."
        ),
    )


def reduce_exposure_cards(portfolio: Portfolio, view: MarketView, risk: PortfolioRisk, ref: Reference) -> list[Card]:
    cards: list[Card] = []
    exited: set[int] = set()
    reduced_by_cluster: dict[str, float] = {}

    for i, position in enumerate(portfolio.positions):
        failing = [
            s for s in position_exposures(position, ref)
            if s in view.assessments and view.assessments[s].probs.p_failure >= FAILURE_VETO_THRESHOLD
        ]
        if not failing:
            continue
        worst = max(failing, key=lambda s: view.assessments[s].probs.p_failure)
        entry = respond(ref.assets[worst], view.assessments[worst])
        exited.add(i)
        cluster = ref.assets[worst].cluster
        if cluster:
            reduced_by_cluster[cluster] = reduced_by_cluster.get(cluster, 0.0) + position.amount_usd
        cards.append(
            _reduce_card(
                position.asset, position.venue_id, entry.destination or SAFE_RAIL, position.amount_usd,
                headline=f"Exit {position.asset} position: {worst} is failing",
                explanation=[entry.rationale, f"Moves ${position.amount_usd:,.0f} out of the affected position."],
            )
        )

    for breach in risk.cap_breaches:
        remaining = breach.excess_usd - reduced_by_cluster.get(breach.cluster, 0.0)
        if remaining <= 0:
            continue
        in_cluster = [
            (i, p) for i, p in enumerate(portfolio.positions)
            if i not in exited and any(ref.assets[s].cluster == breach.cluster for s in position_exposures(p, ref))
        ]
        if not in_cluster:
            continue
        _, source = max(in_cluster, key=lambda ip: position_expected_loss(ip[1], view, ref) / max(ip[1].amount_usd, 1e-9))
        amount = min(remaining, source.amount_usd)
        cards.append(
            _reduce_card(
                source.asset, source.venue_id, SAFE_RAIL, amount,
                headline=f"Trim {breach.cluster} exposure to {breach.cap:.0%} of NAV",
                explanation=[
                    f"{breach.cluster} is {breach.share:.0%} of your portfolio; your tier caps one stablecoin cluster at {breach.cap:.0%}.",
                    "A de-peg in one coin raises the odds of the others, so concentration is risk.",
                    f"Moves ${amount:,.0f} to the onshore money-market rail.",
                ],
            )
        )
    return cards


def _reduce_card(
    asset: str, from_venue: str | None, destination: str, amount: float, *, headline: str, explanation: list[str]
) -> Card:
    return Card(
        label=CardLabel.REDUCE_EXPOSURE,
        candidate=Candidate(
            venue_id=destination,
            from_venue_id=from_venue,
            action=ActionType.REDUCE_EXPOSURE,
            asset_in=asset,
            amount_usd=amount,
            apy=0.0,
        ),
        mode=AutonomyMode.PROPOSE,
        headline=headline,
        explanation=explanation,
    )


def opportunity_cards(
    view: MarketView,
    snapshot: MarketSnapshot,
    ref: Reference,
    budget_usd: float,
    costs: float = DEFAULT_DISCOUNT_COSTS,
) -> list[Card]:
    """Offer to buy a temporarily mispriced asset when the recovery-adjusted edge clears the margin of safety.
    Always a proposal, never automatic."""
    cards: list[Card] = []
    if budget_usd <= 0:
        return cards
    for symbol, a in sorted(view.assessments.items()):
        if a.discount_to_fv <= 0 or a.probs.dominant != "distress":
            continue
        asset = ref.assets[symbol]
        days = expected_recovery_days(snapshot.pegs[symbol].redemption_status)
        edge = recovery_edge(a.price, a, asset.reserve_quality, costs, snapshot.hurdle_rate, recovery_days=days)
        if edge < MIN_OPPORTUNITY_EDGE:
            continue
        cards.append(
            Card(
                label=CardLabel.OPPORTUNITY,
                candidate=Candidate(
                    venue_id=symbol, action=ActionType.BUY_DISCOUNT, asset_in=symbol, amount_usd=budget_usd, apy=edge
                ),
                mode=AutonomyMode.PROPOSE,
                headline=f"Buy {symbol} at {a.price:.3f}: expected {_pct(edge)} after recovery odds and costs",
                explanation=[
                    f"Fair value {a.fair_value:.3f} from reserves and redemption terms (not a moving average).",
                    f"P(recover) {a.probs.p_recover:.0%}, P(permanent failure) {a.probs.p_failure:.1%}.",
                    f"If it fails, about {asset.reserve_quality:.0%} of fair value is left; costs {costs:.1%} and ~{days:.0f} days of waiting included.",
                    f"Recovery-adjusted edge {_pct(edge)} on ${budget_usd:,.0f}. Proposal only — never automatic.",
                ],
            )
        )
    return sorted(cards, key=lambda c: c.candidate.apy, reverse=True)

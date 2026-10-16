"""/api/mandate/*: parse a request, propose Good/Better/Best through the agent graph, execute the user's pick."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tecc_brain.api.deps import Account, ProposalCache, Scenario, VaultIn, get_proposals, get_ref, get_store
from tecc_brain.graph.pipeline import PipelineResult, load_or_create_profile, run_pipeline
from tecc_brain.intent.parser import default_parser
from tecc_brain.intent.rules import ParseOutcome
from tecc_brain.learning.store import ProfileStore
from tecc_brain.learning.update import FeedbackEvent, Signal, learn
from tecc_brain.market import SnapshotSource
from tecc_brain.models import AutonomyMode, Card, CardLabel, ExecutionIntent, usd_to_onchain
from tecc_brain.reference import Reference
from tecc_brain.strategy.portfolio import load_demo_portfolio

router = APIRouter(prefix="/api/mandate", tags=["mandate"])


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    account: Account = "demo"


class ProposeRequest(ParseRequest):
    scenario: Scenario = "demo"
    vault: VaultIn = VaultIn()


class ProposeResponse(PipelineResult):
    proposal_id: str | None = None


class ExecuteRequest(BaseModel):
    proposal_id: str = Field(min_length=1, max_length=64)
    label: CardLabel
    venue_id: str | None = Field(None, description="Needed only when several cards share a label")


class ExecuteResponse(BaseModel):
    mode: AutonomyMode
    intent: ExecutionIntent
    learned: list[str]
    message: str


@router.post("/parse", response_model=ParseOutcome)
def parse(req: ParseRequest, ref: Reference = Depends(get_ref)) -> ParseOutcome:
    portfolio = load_demo_portfolio() if req.account == "demo" else None
    return default_parser().parse(req.text, ref, portfolio)


@router.post("/propose", response_model=ProposeResponse)
def propose(
    req: ProposeRequest,
    store: ProfileStore = Depends(get_store),
    proposals: ProposalCache = Depends(get_proposals),
    ref: Reference = Depends(get_ref),
) -> ProposeResponse:
    vault = req.vault.to_state()
    result = run_pipeline(req.text, req.account, market=SnapshotSource(req.scenario), store=store, vault=vault, ref=ref)
    pid = proposals.add(req.account, result, vault) if result.decision is not None and result.decision.cards else None
    return ProposeResponse(**result.model_dump(), proposal_id=pid)


def _pick_signal(chosen: Card, cards: list[Card]) -> Signal | None:
    """Safer than BEST → PICK_SAFER; riskier than BETTER (incl. a de-peg opportunity) → PICK_RISKIER."""
    labels = {c.label for c in cards}
    if chosen.label == CardLabel.GOOD and CardLabel.BEST in labels:
        return Signal.PICK_SAFER
    if chosen.label == CardLabel.OPPORTUNITY:
        return Signal.PICK_RISKIER
    if chosen.label == CardLabel.BEST and CardLabel.BETTER in labels:
        return Signal.PICK_RISKIER
    return None


@router.post("/execute", response_model=ExecuteResponse)
def execute(
    req: ExecuteRequest,
    store: ProfileStore = Depends(get_store),
    proposals: ProposalCache = Depends(get_proposals),
    ref: Reference = Depends(get_ref),
) -> ExecuteResponse:
    proposal, first = proposals.claim(req.proposal_id)
    if proposal is None:
        raise HTTPException(404, "unknown or expired proposal")
    if not first:
        raise HTTPException(409, "this proposal was already executed")
    decision = proposal.result.decision
    assert decision is not None
    matches = [c for c in decision.cards if c.label == req.label and (req.venue_id is None or c.candidate.venue_id == req.venue_id)]
    if decision.mode == AutonomyMode.BLOCKED or len(matches) != 1:
        proposals.release(proposal.id)  # a bad request must not burn the proposal
        if decision.mode == AutonomyMode.BLOCKED:
            raise HTTPException(409, "the Brain blocked this request")
        raise HTTPException(422, "that card was not offered" if not matches else "several cards share this label; pass venue_id")
    card = matches[0]

    learned: list[str] = []
    signal = _pick_signal(card, decision.cards)
    if signal is not None:
        profile = load_or_create_profile(store, proposal.account)
        event = FeedbackEvent(event_id=f"pick:{proposal.id}", signal=signal, venue_id=card.candidate.venue_id,
                              amount_usd=card.candidate.amount_usd, at=datetime.now(timezone.utc))
        outcome = learn(profile, event, ref=ref)
        store.save(outcome.profile)
        learned = outcome.changes

    cand = card.candidate
    venue = ref.venues.get(cand.venue_id)
    amount = cand.amount_usd
    needs_faceid = amount > proposal.vault.remaining_usd
    intent = ExecutionIntent(
        card_label=card.label, venue_id=cand.venue_id, action=cand.action, asset_in=cand.asset_in,
        amount_usd=amount, amount_onchain=usd_to_onchain(amount),
        target_address=venue.target_address if venue else None,
        status="breakout_required" if needs_faceid else "pending_signature",
        detail=f"radius left today ${proposal.vault.remaining_usd:,.0f}",
    )
    message = (
        f"${amount:,.0f} exceeds today's ${proposal.vault.remaining_usd:,.0f} radius: confirm with FaceID to break the tether."
        if needs_faceid
        else f"Approved: ${amount:,.0f} will be signed with the session key inside the vault's radius."
    )
    return ExecuteResponse(mode=card.mode, intent=intent, learned=learned, message=message)

"""/api/mandate/*: parse a request, propose Good/Better/Best through the agent graph, execute the user's pick.

Free text goes through a confirm/revise loop before the Brain sees it:

    /draft (≤ 1 + MAX_REVISIONS times) ─▶ /confirm {draft_id, version} ─▶ /propose {draft_id} ─▶ /execute

* /draft is rate-limited per account (optionally also per client IP) before any parser or model runs; every revision is
  firewalled on its own, and each refusal is a strike (3 in 30 min lock drafting for 15 min).
* /draft loads the caller's BrainProfile and personalises the suggestion with what it already learned
  (standing avoid-preferences, Beta approval posteriors, the τ-scaled soft tether). Everything it adds is shown.
* /confirm locks the structured Mandate the user saw, by content hash (`version`); /propose runs exactly that
  Mandate (never a re-parse of the text) and only once.

The options list (/evaluate_options) and plain `/propose {text}` keep working unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from tecc_brain.api.deps import (
    Account,
    DraftCache,
    ProposalCache,
    RateLimiter,
    Scenario,
    VaultIn,
    client_key,
    RouterExecutor,
    card_key,
    get_brain_llm,
    get_drafts,
    get_limiter,
    get_news_sentinel,
    get_proposals,
    get_ref,
    get_router,
    get_store,
)
from tecc_brain.graph.brain import BrainLLM
from tecc_brain.graph.pipeline import PipelineResult, load_or_create_profile, run_pipeline
from tecc_brain.intent.parser import default_parser
from tecc_brain.intent.rules import ParseOutcome
from tecc_brain.learning.store import ProfileStore
from tecc_brain.learning.update import FeedbackEvent, Signal, learn
from tecc_brain.market import SnapshotSource
from tecc_brain.onchain.executor import MarketRouter
from tecc_brain.models import (
    APPROVAL_PRIOR, AutonomyMode, BrainProfile, Card, CardLabel, ExecutionIntent, Mandate, VaultState, usd_to_onchain,
)
from tecc_brain.reference import Reference
from tecc_brain.sentinel import LexiconSentinel, apply_signal
from tecc_brain.sentinel.blended import NewsRiskSentinel, make_news_hook
from tecc_brain.strategy.planner import mandate_amount_usd, protocol_stance, soft_limit
from tecc_brain.strategy.portfolio import load_demo_portfolio

router = APIRouter(prefix="/api/mandate", tags=["mandate"])

DRAFT_ID_PATTERN = r"^[0-9a-f]{32}$"


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    account: Account = "demo"


class DraftStatus(str, Enum):
    NEEDS_REVISION = "needs_revision"  # refused by the firewall, or the parser could not understand it
    READY = "ready"  # a suggested Mandate is waiting for the user to confirm or revise
    CONFIRMED = "confirmed"  # locked; pass draft_id to /propose
    EXHAUSTED = "exhausted"  # no usable suggestion and no revisions left: steer the user to the options list


class DraftMandateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    account: Account = "demo"
    draft_id: str | None = Field(None, pattern=DRAFT_ID_PATTERN,
                                 description="Pass the previous draft_id to revise it; omit to start a new draft.")
    scenario: Scenario = "demo"
    vault: VaultIn = Field(default_factory=VaultIn, description="Only used for the autonomy preview; /propose re-reads it")


class VenuePreview(BaseModel):
    venue_id: str
    approval_posterior: float = Field(ge=0, le=1, description="Beta posterior mean α/(α+β) of your past approvals")
    observations: int = Field(ge=0, description="Signals learned for this venue (0 = no history, prior only)")


class Personalization(BaseModel):
    """What the BrainProfile changed or predicts at draft time — all shown to the user before they confirm."""

    tier: str
    lam: float
    tau: float
    added_constraints: list[str] = Field(default_factory=list, description="From standing preferences, e.g. avoid:curve")
    constraint_reasons: list[str] = Field(default_factory=list)
    venue_preview: list[VenuePreview] = Field(default_factory=list, description="Display only; the Brain decides")
    estimated_usd: float | None = None
    soft_limit_usd: float
    autonomy_preview: Literal["likely_auto", "needs_approval", "needs_faceid"]
    warnings: list[str] = Field(default_factory=list)


class DraftMandateResponse(BaseModel):
    draft_id: str
    version: str = Field(description="Echo this to /confirm: it pins exactly the suggestion shown")
    status: DraftStatus
    revision: int
    revisions_left: int
    suggested: Mandate | None = Field(None, description="The order the Brain will run if confirmed")
    summary: str | None = Field(None, description="One line to show the user before they confirm, e.g. 'Stake 500 USDC for 365 day(s).'")
    personalization: Personalization | None = None
    parse: ParseOutcome


class ConfirmDraftRequest(BaseModel):
    draft_id: str = Field(pattern=DRAFT_ID_PATTERN)
    version: str = Field(pattern=r"^[0-9a-f]{16}$", description="The `version` /draft returned with the summary the user approved")
    account: Account = "demo"


class ConfirmDraftResponse(BaseModel):
    draft_id: str
    status: DraftStatus
    mandate: Mandate
    message: str


def _summary(m: Mandate) -> str:
    avoids = [c.split(":", 1)[1] for c in m.constraints if c.startswith("avoid:")]
    only = [c.split(":", 1)[1] for c in m.constraints if c.startswith("venue:")]
    extra = (f", only via {', '.join(only)}" if only else "") + (f", avoiding {', '.join(avoids)}" if avoids else "")
    return f"{m.action.value.title()} {m.amount:g} {m.asset} for {m.horizon_days} day(s){extra}."


def personalize(
    mandate: Mandate, profile: BrainProfile, vault: VaultState, ref: Reference, estimated_usd: float | None
) -> tuple[Mandate, Personalization]:
    """Apply what the profile already learned, early and visibly. No new math: the latest note per protocol
    (protocol_stance), the Beta approval posteriors, and the τ-scaled soft tether the planner itself uses."""
    explicit_only = {c.split(":", 1)[1] for c in mandate.constraints if c.startswith("venue:")}
    added: list[str] = []
    reasons: list[str] = []
    for protocol in sorted({v.protocol for v in ref.venues.values()}):
        stance = protocol_stance(profile, protocol)
        constraint = f"avoid:{protocol}"
        # What the user typed in THIS request beats an older note ("only via curve" overrides "avoid curve").
        if stance is None or stance.polarity > 0 or protocol in explicit_only or constraint in mandate.constraints:
            continue
        added.append(constraint)
        reasons.append(f"From your earlier note: “{stance.quote}”." if stance.quote else f"You previously asked to avoid {protocol}.")
    constraints = mandate.constraints + added
    suggested = mandate.model_copy(update={"constraints": constraints})

    avoid = {c.split(":", 1)[1] for c in constraints if c.startswith("avoid:")}
    fits = [v for v in ref.venues.values() if mandate.asset in v.accepts and v.protocol not in avoid
            and (not explicit_only or v.protocol in explicit_only)]
    prior = sum(APPROVAL_PRIOR)
    preview = sorted(
        (VenuePreview(venue_id=v.id, approval_posterior=round(profile.approval_mean(v.id), 4),
                      observations=max(0, round(sum(profile.approvals.get(v.id, APPROVAL_PRIOR)) - prior)))
         for v in fits),
        key=lambda p: (p.observations > 0, p.approval_posterior, p.venue_id), reverse=True,
    )[:3]

    warnings: list[str] = []
    if not fits:
        warnings.append(f"No venue accepts {mandate.asset} under these constraints; the Brain will have nothing to offer.")
    elif all(v.tier > profile.tier for v in fits):
        warnings.append(f"Every venue for {mandate.asset} is riskier than your {profile.tier.name.lower()} tier; "
                        "the Brain will block this unless you change your tier.")
    if estimated_usd is None:
        warnings.append(f"No market price for {mandate.asset}: the amount cannot be verified, so nothing will run automatically.")

    limit = soft_limit(profile, vault)
    if estimated_usd is not None and estimated_usd > vault.remaining_usd:
        autonomy: Literal["likely_auto", "needs_approval", "needs_faceid"] = "needs_faceid"
    elif estimated_usd is None or estimated_usd > limit:
        autonomy = "needs_approval"
    else:
        autonomy = "likely_auto"
    return suggested, Personalization(
        tier=profile.tier.name.lower(), lam=profile.lam, tau=profile.tau, added_constraints=added,
        constraint_reasons=reasons, venue_preview=preview, estimated_usd=estimated_usd, soft_limit_usd=limit,
        autonomy_preview=autonomy, warnings=warnings,
    )


@router.post("/draft", response_model=DraftMandateResponse)
def draft_mandate(
    req: DraftMandateRequest,
    request: Request,
    drafts: DraftCache = Depends(get_drafts),
    limiter: RateLimiter = Depends(get_limiter),
    store: ProfileStore = Depends(get_store),
    ref: Reference = Depends(get_ref),
) -> DraftMandateResponse:
    """Step 1: turn free text into a suggested order the user reads back (start, or revise with `draft_id`)."""
    client, account = client_key(request), f"account:{req.account}"
    # Budgets first: nothing below (profile I/O, parser, a future LLM) runs for a throttled caller.
    if req.draft_id is None:
        limiter.check("draft:start:account", account)
        if limiter.by_client:
            limiter.check("draft:start:client", client)
    limiter.check("draft:any:account", account)
    if limiter.by_client:
        limiter.check("draft:any:client", client)

    profile = load_or_create_profile(store, req.account)
    portfolio = load_demo_portfolio() if req.account == "demo" else None
    parse = default_parser().parse(req.text, ref, portfolio)  # firewall → sieve → parser, per revision
    if not parse.verdict.allowed:
        limiter.strike(*limiter.keys(account, client))

    suggested: Mandate | None = None
    personalization: Personalization | None = None
    if parse.verdict.allowed and parse.mandate is not None:
        estimated_usd, _ = mandate_amount_usd(parse.mandate, SnapshotSource(req.scenario).snapshot())
        suggested, personalization = personalize(parse.mandate, profile, req.vault.to_state(), ref, estimated_usd)

    if req.draft_id is None:
        draft = drafts.start(req.account, client, req.text, parse, suggested, personalization)
    else:
        draft = drafts.revise(req.draft_id, req.account, client, req.text, parse, suggested, personalization)

    left = drafts.max_revisions - draft.revision
    status = DraftStatus.READY if suggested is not None else (DraftStatus.NEEDS_REVISION if left > 0 else DraftStatus.EXHAUSTED)
    return DraftMandateResponse(
        draft_id=draft.id, version=draft.version, status=status, revision=draft.revision, revisions_left=left,
        suggested=suggested, summary=_summary(suggested) if suggested is not None else None,
        personalization=personalization, parse=parse,
    )


@router.post("/confirm", response_model=ConfirmDraftResponse)
def confirm_draft(
    req: ConfirmDraftRequest, drafts: DraftCache = Depends(get_drafts), limiter: RateLimiter = Depends(get_limiter)
) -> ConfirmDraftResponse:
    """Step 2: the user approved the suggestion /draft showed them. Locks that exact Mandate (by `version`)."""
    limiter.check("confirm:account", f"account:{req.account}")
    draft = drafts.confirm(req.draft_id, req.account, req.version)
    assert draft.suggested is not None
    return ConfirmDraftResponse(draft_id=draft.id, status=DraftStatus.CONFIRMED, mandate=draft.suggested,
                                message="Confirmed. Call /propose with this draft_id.")


class ProposeRequest(BaseModel):
    account: Account = "demo"
    scenario: Scenario = "demo"
    vault: VaultIn = VaultIn()
    headline: str | None = Field(None, max_length=500, description="Optional breaking headline for the NLP Risk Sentinel")
    text: str | None = Field(None, min_length=1, max_length=2000, description="Free text order. Omit when draft_id is set.")
    draft_id: str | None = Field(
        None, pattern=DRAFT_ID_PATTERN,
        description="A confirmed draft from /api/mandate/confirm (preferred). Its locked Mandate runs exactly as "
                    "confirmed, once; `text` is ignored when this is set.",
    )

    @model_validator(mode="after")
    def _one_of_text_or_draft(self) -> "ProposeRequest":
        if not self.draft_id and not self.text:
            raise ValueError("either `text` or a confirmed `draft_id` is required")
        return self


class ProposeResponse(PipelineResult):
    proposal_id: str | None = None


class ExecuteRequest(BaseModel):
    proposal_id: str = Field(min_length=1, max_length=64)
    account: Account = Field("demo", description="Must be the account the proposal was made for")
    label: CardLabel
    venue_id: str | None = Field(None, description="Needed only when several cards share a label")
    option_id: str | None = Field(None, max_length=64, description="Options-list proposals: the option to approve")


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
    drafts: DraftCache = Depends(get_drafts),
    ref: Reference = Depends(get_ref),
    brain_llm: BrainLLM | None = Depends(get_brain_llm),
    sentinel: NewsRiskSentinel = Depends(get_news_sentinel),
    router: MarketRouter = Depends(get_router),
) -> ProposeResponse:
    """With `draft_id`: run the confirmed, locked Mandate (never a re-parse; one-shot). With `text`: the original
    free-text path, unchanged."""
    mandate = drafts.consume(req.draft_id, req.account) if req.draft_id is not None else None
    text = mandate.raw_text if mandate is not None else req.text
    assert text is not None  # guaranteed by the model_validator above

    vault = req.vault.to_state()
    # Agent 1 is the upgraded sentinel (same as /evaluate_options and the hourly monitor); an optional breaking
    # headline from the request is layered on top of it, as before.
    blended = make_news_hook(sentinel, ref)
    signal = LexiconSentinel(ref).score(req.headline) if req.headline else None

    def news_hook(snap):
        snap = blended(snap)
        return apply_signal(snap, signal) if signal is not None else snap

    result = run_pipeline(text, req.account, mandate=mandate, market=SnapshotSource(req.scenario), store=store,
                          vault=vault, ref=ref, news_hook=news_hook, brain_llm=brain_llm,
                          executor=RouterExecutor(router, vault.tether_radius_usd))
    ran = {result.intent.venue_id: result.intent.amount_usd} if result.intent and result.intent.status in ("submitted", "simulated", "signed") else {}
    pid = (proposals.add(req.account, result, vault, auto_executed_usd=ran)
           if result.decision is not None and result.decision.cards else None)
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
    router: MarketRouter = Depends(get_router),
) -> ExecuteResponse:
    """The user approves one card. The Brain's per-card verdict is binding here: a BLOCKED card (AI veto) is
    refused, a BREAKOUT card always needs FaceID; only what has not already run automatically is executed, and
    it goes through the shared MarketRouter (cross-chain tether radius, live vault or honest simulation)."""
    peek = proposals.get(req.proposal_id)
    if peek is None or peek.account != req.account:  # same answer either way: don't reveal other accounts' ids
        raise HTTPException(404, "unknown or expired proposal")
    proposal, first = proposals.claim(req.proposal_id)
    if proposal is None:
        raise HTTPException(404, "unknown or expired proposal")
    if not first:
        raise HTTPException(409, "this proposal was already executed")
    decision = proposal.result.decision
    assert decision is not None
    matches = [c for c in decision.cards if c.label == req.label
               and (req.venue_id is None or c.candidate.venue_id == req.venue_id)
               and (req.option_id is None or c.option_id == req.option_id)]
    if decision.mode == AutonomyMode.BLOCKED or len(matches) != 1:
        proposals.release(proposal.id)  # a bad request must not burn the proposal
        if decision.mode == AutonomyMode.BLOCKED:
            raise HTTPException(409, "the Brain blocked this request")
        raise HTTPException(422, "that card was not offered" if not matches
                            else "several cards share this label; pass venue_id or option_id")
    card = matches[0]
    if card.mode == AutonomyMode.BLOCKED:
        proposals.release(proposal.id)  # another card of the same proposal may still be approved
        raise HTTPException(409, "the AI Brain vetoed this option; it cannot be executed")

    already = proposal.auto_executed_usd.get(card_key(card), 0.0)
    cand = card.candidate
    amount = round(cand.amount_usd - already, 2)
    if amount <= 0:
        proposals.release(proposal.id)
        raise HTTPException(409, "this option already ran in full automatically")

    learned: list[str] = []
    signal = _pick_signal(card, decision.cards)
    if signal is not None:
        profile = load_or_create_profile(store, proposal.account)
        event = FeedbackEvent(event_id=f"pick:{proposal.id}", signal=signal, venue_id=cand.venue_id,
                              amount_usd=cand.amount_usd, at=datetime.now(timezone.utc))
        outcome = learn(profile, event, ref=ref)
        store.save(outcome.profile)
        learned = outcome.changes

    venue = ref.venues.get(cand.venue_id)
    radius_left = max(0.0, proposal.vault.remaining_usd - sum(proposal.auto_executed_usd.values()))
    needs_faceid = card.mode == AutonomyMode.BREAKOUT or amount > radius_left
    intent = ExecutionIntent(
        card_label=card.label, venue_id=cand.venue_id, action=cand.action, asset_in=cand.asset_in,
        amount_usd=amount, amount_onchain=usd_to_onchain(amount),
        target_address=venue.target_address if venue else None, market=card.market,
        status="breakout_required" if needs_faceid else "pending_signature",
        detail=f"radius left today ${radius_left:,.0f}",
    )
    if needs_faceid:
        why = ("the AI Brain requires biometric confirmation for this option" if card.mode == AutonomyMode.BREAKOUT
               else f"${amount:,.0f} exceeds today's ${radius_left:,.0f} radius")
        return ExecuteResponse(mode=card.mode, intent=intent, learned=learned,
                               message=f"{why[0].upper()}{why[1:]}: confirm with FaceID to break the tether.")

    sent = router.submit(intent, proposal.account, limit_usd=proposal.vault.tether_radius_usd)
    message = {
        "submitted": f"Executed: ${amount:,.0f} signed with the session key and accepted by the vault.",
        "simulated": f"Approved: ${amount:,.0f} routed to the {card.market} market (simulated — no live node configured).",
    }.get(sent.status, f"Not executed: {sent.detail}")
    return ExecuteResponse(mode=card.mode, intent=sent, learned=learned, message=message)

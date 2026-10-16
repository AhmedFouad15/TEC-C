"""/api/profile/*, /api/review/sync, /api/levers/*: the "Your Brain" panel and the learning loop."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from tecc_brain.api.deps import Account, get_ref, get_store
from tecc_brain.graph.pipeline import load_or_create_profile
from tecc_brain.learning.levers import LeverAction, LeverState, approval_rate, lever_actions
from tecc_brain.learning.onboarding import QUIZ, OnboardingResult, QuizQuestion, onboard, score_quiz
from tecc_brain.learning.store import ProfileStore, account_key
from tecc_brain.learning.update import learn
from tecc_brain.models import LAMBDA_BANDS, BrainProfile, FeedbackEvent, RiskTier, VaultState
from tecc_brain.reference import Reference
from tecc_brain.strategy.planner import soft_limit

router = APIRouter(tags=["profile"])

MAX_EVENTS_PER_SYNC = 200


class VenueApproval(BaseModel):
    venue_id: str
    approval: float
    affinity: float
    alpha: float
    beta: float


class ProfileView(BaseModel):
    account: str
    tier: RiskTier
    tier_name: str
    lam: float
    lam_band: tuple[float, float]
    tau: float
    soft_limit_usd: float
    approval_rate_7d: float | None
    approvals: list[VenueApproval]
    likes: list[str]
    dislikes: list[str]
    cost_factors: dict[str, float]
    recent: list[FeedbackEvent]


def profile_view(p: BrainProfile, radius_usd: float = 500.0) -> ProfileView:
    latest: dict[str, int] = {}
    for pref in p.preferences:
        if pref.protocol:
            latest[pref.protocol] = pref.polarity
    return ProfileView(
        account=p.account, tier=p.tier, tier_name=p.tier.name.title(), lam=p.lam, lam_band=LAMBDA_BANDS[p.tier],
        tau=p.tau, soft_limit_usd=soft_limit(p, VaultState(tether_radius_usd=radius_usd)),
        approval_rate_7d=approval_rate(p, datetime.now(timezone.utc)),
        approvals=[
            VenueApproval(venue_id=v, approval=p.approval_mean(v), affinity=p.affinity(v), alpha=a, beta=b)
            for v, (a, b) in sorted(p.approvals.items())
        ],
        likes=sorted(k for k, v in latest.items() if v > 0),
        dislikes=sorted(k for k, v in latest.items() if v < 0),
        cost_factors=p.cost_factors,
        recent=p.history[-10:],
    )


def _account(account: str) -> str:
    try:
        account_key(account)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return account


@router.get("/api/profile/quiz", response_model=list[QuizQuestion])
def quiz() -> list[QuizQuestion]:
    return list(QUIZ)


class OnboardRequest(BaseModel):
    account: Account
    answers: dict[str, str]
    reset: bool = False


class OnboardResponse(BaseModel):
    result: OnboardingResult
    profile: ProfileView


@router.post("/api/profile/onboard", response_model=OnboardResponse)
def onboard_user(req: OnboardRequest, store: ProfileStore = Depends(get_store)) -> OnboardResponse:
    if store.load(req.account) is not None and not req.reset:
        raise HTTPException(409, "this account already has a learned profile; pass reset=true to start over")
    try:
        result = score_quiz(req.answers)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    profile = onboard(req.account, req.answers)
    store.save(profile)
    return OnboardResponse(result=result, profile=profile_view(profile))


@router.get("/api/profile/{account}", response_model=ProfileView)
def get_profile(
    account: str, radius_usd: float = Query(500.0, ge=0, le=1e9), store: ProfileStore = Depends(get_store)
) -> ProfileView:
    return profile_view(load_or_create_profile(store, _account(account)), radius_usd)


class SyncRequest(BaseModel):
    account: Account
    events: list[FeedbackEvent] = Field(max_length=MAX_EVENTS_PER_SYNC)


class SyncItem(BaseModel):
    event_id: str
    applied: bool
    changes: list[str]


class SyncResponse(BaseModel):
    applied: int
    duplicates: int
    results: list[SyncItem]
    profile: ProfileView


@router.post("/api/review/sync", response_model=SyncResponse)
def review_sync(
    req: SyncRequest, store: ProfileStore = Depends(get_store), ref: Reference = Depends(get_ref)
) -> SyncResponse:
    """Apply Morning Review events (Phase 7 pulls them from the chain; until then the UI/simulator posts them)."""
    profile = load_or_create_profile(store, req.account)
    results = []
    for event in sorted(req.events, key=lambda e: e.at):
        outcome = learn(profile, event, ref=ref)
        profile = outcome.profile
        results.append(SyncItem(event_id=event.event_id, applied=outcome.applied, changes=outcome.changes))
    store.save(profile)
    applied = sum(r.applied for r in results)
    return SyncResponse(applied=applied, duplicates=len(results) - applied, results=results, profile=profile_view(profile))


class LeversResponse(BaseModel):
    actions: list[LeverAction]


@router.post("/api/levers/{account}", response_model=LeversResponse)
def levers(account: str, state: LeverState, store: ProfileStore = Depends(get_store)) -> LeversResponse:
    profile = load_or_create_profile(store, _account(account))
    return LeversResponse(actions=lever_actions(profile, state, datetime.now(timezone.utc)))

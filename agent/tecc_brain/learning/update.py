"""Rewards and penalties: how one review signal changes what the Brain believes about its user (BRAIN_DESIGN §3.2).

Three things are learned, all bounded:
* approval Beta(α, β) per venue — "would this user approve the Brain acting here?"
* τ (trust) — scales the Brain's soft tether; earned slowly, lost fast
* λ (loss aversion) — how heavily expected losses weigh in the score; stays inside the tier's band

Safety rules: penalties are heavier than rewards, tiny trades count less (value weight), trust can rise at most
+0.05 per day while falls are uncapped, λ never leaves its tier band, old feedback fades with a 30-day half-life,
and the same event applied twice changes nothing. Learning never touches the market's regime model.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from tecc_brain.models import (
    APPROVAL_PRIOR,
    LAMBDA_BANDS,
    LAMBDA_START,
    BrainProfile,
    FeedbackEvent,
    RiskTier,
    Signal,
)

__all__ = ["FeedbackEvent", "LearningResult", "Signal", "decay", "learn", "new_profile", "value_weight"]

START_TAU = 0.6
TAU_DAILY_GAIN_CAP = 0.05  # mirrors the vault's ≤10 %/day radius growth: autonomy is earned slowly
DECAY_HALF_LIFE_DAYS = 30.0
HISTORY_DAYS = 90
MAX_SEEN_EVENTS = 2000
VALUE_WEIGHT_MIN, VALUE_WEIGHT_MAX = 0.5, 2.0

# signal -> (Δα, Δβ, Δτ, λ multiplier, scale Δα and Δτ by the value weight?)
# Penalties are never discounted by trade size: a flagged $5 trade is still a flagged trade.
RULES: dict[Signal, tuple[float, float, float, float, bool]] = {
    Signal.RATIFY: (1.0, 0.0, +0.02, 1.00, True),
    Signal.FLAG: (0.0, 3.0, -0.15, 1.10, False),
    Signal.NOTE_PENALTY: (0.0, 1.5, -0.07, 1.00, False),
    Signal.NOTE: (0.0, 0.0, 0.0, 1.00, False),  # note content is applied by learning.notes (05-02)
    Signal.BREAKOUT_ACCEPT: (1.0, 0.0, +0.01, 1.00, False),
    Signal.BREAKOUT_REJECT: (0.0, 2.0, -0.05, 1.05, False),
    Signal.PICK_SAFER: (0.5, 0.0, 0.0, 1.05, False),
    Signal.PICK_RISKIER: (0.5, 0.0, 0.0, 0.95, False),
    Signal.IGNORED: (0.0, 0.0, 0.0, 1.00, False),
}


class LearningResult(BaseModel):
    profile: BrainProfile
    changes: list[str]
    applied: bool


def new_profile(account: str, tier: RiskTier) -> BrainProfile:
    return BrainProfile(account=account, tier=tier, lam=LAMBDA_START[tier], tau=START_TAU)


def value_weight(amount_usd: float) -> float:
    """v = clamp(1 + log10(usd / 100), 0.5, 2.0): $100 counts once, $1,000+ twice, dust half."""
    if amount_usd <= 0:
        return VALUE_WEIGHT_MIN
    return min(VALUE_WEIGHT_MAX, max(VALUE_WEIGHT_MIN, 1.0 + math.log10(amount_usd / 100.0)))


def decay(profile: BrainProfile, now: datetime) -> BrainProfile:
    """Move every approval Beta toward the prior: the gap halves every 30 days without news."""
    p = profile.model_copy(deep=True)
    if p.updated_at is None:
        p.updated_at = now
        return p
    days = (now - p.updated_at).total_seconds() / 86400.0
    if days <= 0:
        return p
    keep = 0.5 ** (days / DECAY_HALF_LIFE_DAYS)
    a0, b0 = APPROVAL_PRIOR
    p.approvals = {v: (a0 + (a - a0) * keep, b0 + (b - b0) * keep) for v, (a, b) in p.approvals.items()}
    p.updated_at = now
    return p


def clamp_lambda(tier: RiskTier, lam: float) -> float:
    lo, hi = LAMBDA_BANDS[tier]
    return min(hi, max(lo, lam))


def _day(at: datetime) -> str:
    return at.astimezone(timezone.utc).date().isoformat()


def learn(profile: BrainProfile, event: FeedbackEvent) -> LearningResult:
    """Apply one signal. Pure: returns a new profile and human-readable change lines for "Your Brain"."""
    if event.event_id in profile.seen_events:
        return LearningResult(profile=profile, changes=["Already learned from this event."], applied=False)

    p = decay(profile, event.at)
    changes: list[str] = []
    d_alpha, d_beta, d_tau, lam_mult, weighted = RULES[event.signal]
    v = value_weight(event.amount_usd) if weighted else 1.0
    d_alpha *= v
    d_tau *= v

    if event.venue_id is not None and (d_alpha or d_beta):
        before = p.approval_mean(event.venue_id)
        a, b = p.approvals.get(event.venue_id, APPROVAL_PRIOR)
        p.approvals[event.venue_id] = (a + d_alpha, b + d_beta)
        changes.append(f"Approval for {event.venue_id}: {before:.0%} → {p.approval_mean(event.venue_id):.0%}.")

    if d_tau:
        before = p.tau
        if d_tau > 0:
            day = _day(event.at)
            room = max(0.0, TAU_DAILY_GAIN_CAP - p.tau_gains.get(day, 0.0))
            gain = min(d_tau, room, 1.0 - p.tau)
            p.tau_gains[day] = p.tau_gains.get(day, 0.0) + gain
            p.tau = p.tau + gain
            if gain < d_tau and room < d_tau:
                changes.append(f"Daily trust cap reached: +{gain:.3f} of +{d_tau:.3f} applied today.")
        else:
            p.tau = max(0.0, p.tau + d_tau)
        if p.tau != before:
            changes.append(f"Trust τ: {before:.2f} → {p.tau:.2f}.")

    if lam_mult != 1.0:
        before = p.lam
        p.lam = clamp_lambda(p.tier, p.lam * lam_mult)
        if p.lam != before:
            changes.append(f"Loss aversion λ: {before:.2f} → {p.lam:.2f}.")
        else:
            changes.append(f"Loss aversion λ stays {p.lam:.2f} (edge of your tier's band).")

    _record(p, event)
    if not changes:
        changes.append(f"Noted ({event.signal.value}); nothing to adjust.")
    return LearningResult(profile=p, changes=changes, applied=True)


def _record(p: BrainProfile, event: FeedbackEvent) -> None:
    assert p.updated_at is not None
    horizon = p.updated_at - timedelta(days=HISTORY_DAYS)
    p.history = [e for e in [*p.history, event] if e.at >= horizon]
    p.seen_events = [*p.seen_events, event.event_id][-MAX_SEEN_EVENTS:]
    oldest_day = (p.updated_at - timedelta(days=7)).date().isoformat()
    p.tau_gains = {d: g for d, g in p.tau_gains.items() if d >= oldest_day}

"""When the Brain pulls the vault's on-chain levers (BRAIN_DESIGN §3.3). Pure decision functions; Phase 7 sends them.

* recordAIHeartbeat — every 12 h (the vault times out after 48 h), or at once if the vault reports it stale.
* autonomousRadiusAdjustment (decrease) — shrink its own radius 10% after 2 flags in 7 days, or while a held cluster
  is under stress. At most once a day, never to 0 (the contract reverts on 0).
* calibrateDynamicRadius — ask the vault to grow the radius (the vault computes the ≤10% step itself) only when
  τ ≥ 0.70, 7-day approval rate ≥ 0.80 and ≥ 3 ratifications in 7 days, and the 24 h cooldown has passed.
  Never in the same round as a shrink.

Both radius levers need the user to have enabled elasticity on-chain; without it the contract reverts.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from tecc_brain.models import BrainProfile, Signal

HEARTBEAT_EVERY = timedelta(hours=12)
WINDOW = timedelta(days=7)
COOLDOWN = timedelta(hours=24)  # TetherGuardHook.CALIBRATION_COOLDOWN; also our own pace for shrinking
SHRINK_AFTER_FLAGS = 2
SHRINK_FACTOR = 0.90
CALIBRATE_MIN_TAU = 0.70
CALIBRATE_MIN_APPROVAL = 0.80
CALIBRATE_MIN_RATIFIES = 3
MIN_ONCHAIN_RADIUS_USD = 1e-8  # one unit of the vault's 8-decimal USD; the contract reverts on 0

POSITIVE = {Signal.RATIFY, Signal.BREAKOUT_ACCEPT}
NEGATIVE = {Signal.FLAG, Signal.NOTE_PENALTY, Signal.BREAKOUT_REJECT}


class LeverState(BaseModel):
    """What the Brain knows about the vault's levers for one account (Phase 7 reads it from TetherGuardHook)."""

    radius_usd: float = Field(ge=0)
    elasticity_enabled: bool = False
    last_step_up_at: datetime | None = None
    last_shrink_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    heartbeat_alive: bool = True
    held_cluster_stressed: bool = False


class LeverAction(BaseModel):
    kind: Literal["heartbeat", "calibrate", "shrink"]
    new_radius_usd: float | None = None
    rationale: str = Field(max_length=120, description="Short: it is written on-chain in AutonomousRadiusAdjusted")


def _recent(profile: BrainProfile, now: datetime, signals: set[Signal]) -> int:
    return sum(1 for e in profile.history if e.signal in signals and now - WINDOW <= e.at <= now)


def approval_rate(profile: BrainProfile, now: datetime) -> float | None:
    """Share of the last 7 days' verdicts that approved the Brain; None without any verdict."""
    good, bad = _recent(profile, now, POSITIVE), _recent(profile, now, NEGATIVE)
    return good / (good + bad) if good + bad else None


def lever_actions(profile: BrainProfile, state: LeverState, now: datetime) -> list[LeverAction]:
    actions: list[LeverAction] = []
    if not state.heartbeat_alive or state.last_heartbeat_at is None or now - state.last_heartbeat_at >= HEARTBEAT_EVERY:
        actions.append(LeverAction(kind="heartbeat", rationale="Brain alive"))
    if not state.elasticity_enabled:
        return actions

    flags = _recent(profile, now, {Signal.FLAG})
    shrink_reason = (
        f"{flags} flags in 7 days" if flags >= SHRINK_AFTER_FLAGS
        else "held stablecoin cluster under stress" if state.held_cluster_stressed
        else None
    )
    if shrink_reason:
        cooled = state.last_shrink_at is None or now - state.last_shrink_at >= COOLDOWN
        target = max(MIN_ONCHAIN_RADIUS_USD, state.radius_usd * SHRINK_FACTOR)
        if cooled and target < state.radius_usd:
            actions.append(LeverAction(kind="shrink", new_radius_usd=target, rationale=f"Brain self-limit -10%: {shrink_reason}"))
        return actions  # never grow while there is a reason to shrink

    rate = approval_rate(profile, now)
    if (
        profile.tau >= CALIBRATE_MIN_TAU
        and rate is not None
        and rate >= CALIBRATE_MIN_APPROVAL
        and _recent(profile, now, {Signal.RATIFY}) >= CALIBRATE_MIN_RATIFIES
        and (state.last_step_up_at is None or now - state.last_step_up_at >= COOLDOWN)
    ):
        actions.append(LeverAction(kind="calibrate", rationale=f"trust {profile.tau:.2f}, approval {rate:.0%} over 7 days"))
    return actions

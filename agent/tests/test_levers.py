from datetime import datetime, timedelta, timezone

import pytest

from tecc_brain.learning.levers import (
    CALIBRATE_MIN_TAU,
    MIN_ONCHAIN_RADIUS_USD,
    LeverState,
    approval_rate,
    lever_actions,
)
from tecc_brain.learning.update import FeedbackEvent, Signal, learn, new_profile
from tecc_brain.models import RiskTier

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def history(*signals_and_ages):
    p = new_profile("u", RiskTier.BALANCED)
    for n, (signal, days_ago) in enumerate(signals_and_ages):
        p = learn(p, FeedbackEvent(event_id=f"e{n}", signal=signal, venue_id="aave_v3_usdc", amount_usd=100,
                                   at=NOW - timedelta(days=days_ago))).profile
    return p


def state(**kw):
    base = dict(radius_usd=500.0, elasticity_enabled=True, last_heartbeat_at=NOW - timedelta(hours=1))
    return LeverState(**{**base, **kw})


def kinds(actions):
    return [a.kind for a in actions]


# --- heartbeat ----------------------------------------------------------------------------------


@pytest.mark.parametrize("hours, due", [(11, False), (12, True), (30, True)])
def test_heartbeat_every_twelve_hours(hours, due):
    actions = lever_actions(new_profile("u", RiskTier.BALANCED), state(last_heartbeat_at=NOW - timedelta(hours=hours)), NOW)
    assert ("heartbeat" in kinds(actions)) is due


def test_heartbeat_due_when_never_sent_or_vault_says_stale():
    assert "heartbeat" in kinds(lever_actions(new_profile("u", RiskTier.BALANCED), state(last_heartbeat_at=None), NOW))
    assert "heartbeat" in kinds(lever_actions(new_profile("u", RiskTier.BALANCED), state(heartbeat_alive=False), NOW))


# --- shrink -------------------------------------------------------------------------------------


def test_two_flags_in_a_week_shrink_the_radius_by_ten_percent():
    [shrink] = [a for a in lever_actions(history((Signal.FLAG, 1), (Signal.FLAG, 3)), state(), NOW) if a.kind == "shrink"]
    assert shrink.new_radius_usd == pytest.approx(450.0)
    assert shrink.rationale and len(shrink.rationale) <= 120


def test_a_flag_older_than_seven_days_does_not_count():
    assert "shrink" not in kinds(lever_actions(history((Signal.FLAG, 1), (Signal.FLAG, 8)), state(), NOW))


def test_a_stressed_held_cluster_shrinks_the_radius():
    actions = lever_actions(new_profile("u", RiskTier.BALANCED), state(held_cluster_stressed=True), NOW)
    assert "shrink" in kinds(actions)


def test_shrink_never_reaches_zero():
    actions = lever_actions(new_profile("u", RiskTier.BALANCED),
                            state(radius_usd=MIN_ONCHAIN_RADIUS_USD, held_cluster_stressed=True), NOW)
    assert "shrink" not in kinds(actions)
    [shrink] = [a for a in lever_actions(new_profile("u", RiskTier.BALANCED),
                                         state(radius_usd=1e-8 * 1.05, held_cluster_stressed=True), NOW)
                if a.kind == "shrink"]
    assert shrink.new_radius_usd >= MIN_ONCHAIN_RADIUS_USD


def test_shrink_at_most_once_a_day():
    s = state(held_cluster_stressed=True, last_shrink_at=NOW - timedelta(hours=5))
    assert "shrink" not in kinds(lever_actions(new_profile("u", RiskTier.BALANCED), s, NOW))


def test_levers_need_elasticity_enabled():
    s = state(held_cluster_stressed=True, elasticity_enabled=False)
    assert kinds(lever_actions(new_profile("u", RiskTier.BALANCED), s, NOW)) == []


# --- calibrate ----------------------------------------------------------------------------------


def trusted(tau=0.75, ratifies=3, extra=()):
    p = history(*[(Signal.RATIFY, 1)] * ratifies, *extra)
    return p.model_copy(update={"tau": tau})


def test_calibrate_when_trusted_approved_and_ratified():
    actions = lever_actions(trusted(), state(), NOW)
    [cal] = [a for a in actions if a.kind == "calibrate"]
    assert cal.new_radius_usd is None  # the vault computes the +10% itself


@pytest.mark.parametrize("profile", [
    pytest.param(lambda: trusted(tau=CALIBRATE_MIN_TAU - 0.01), id="tau-too-low"),
    pytest.param(lambda: trusted(ratifies=2), id="too-few-ratifies"),
    pytest.param(lambda: trusted(ratifies=3, extra=[(Signal.FLAG, 2)]), id="approval-rate-75pct"),
])
def test_no_calibration_without_all_three_conditions(profile):
    assert "calibrate" not in kinds(lever_actions(profile(), state(), NOW))


def test_calibration_respects_the_vault_cooldown():
    assert "calibrate" not in kinds(lever_actions(trusted(), state(last_step_up_at=NOW - timedelta(hours=23)), NOW))
    assert "calibrate" in kinds(lever_actions(trusted(), state(last_step_up_at=NOW - timedelta(hours=24)), NOW))


def test_shrink_wins_over_calibrate():
    actions = lever_actions(trusted(), state(held_cluster_stressed=True), NOW)
    assert "shrink" in kinds(actions) and "calibrate" not in kinds(actions)


def test_approval_rate_counts_only_the_last_seven_days():
    p = history((Signal.RATIFY, 1), (Signal.BREAKOUT_ACCEPT, 2), (Signal.FLAG, 3), (Signal.FLAG, 10))
    assert approval_rate(p, NOW) == pytest.approx(2 / 3)
    assert approval_rate(new_profile("u", RiskTier.BALANCED), NOW) is None

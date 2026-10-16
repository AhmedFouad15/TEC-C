from datetime import datetime, timedelta, timezone

import pytest

from tecc_brain.learning.update import FeedbackEvent, Signal, learn, new_profile, value_weight
from tecc_brain.models import APPROVAL_PRIOR, LAMBDA_BANDS, LAMBDA_START, BrainProfile, RiskTier
from tecc_brain.strategy.planner import load_demo_profile

T0 = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)
AAVE = "aave_v3_usdc"


def event(signal, n=0, venue=AAVE, usd=100.0, at=T0, note=""):
    return FeedbackEvent(event_id=f"{signal.value}-{n}-{at.isoformat()}", signal=signal, venue_id=venue,
                         amount_usd=usd, at=at, note=note)


def run(profile, events):
    for e in events:
        profile = learn(profile, e).profile
    return profile


# --- value weight -------------------------------------------------------------------------------


@pytest.mark.parametrize("usd, v", [(100, 1.0), (10, 0.5), (1, 0.5), (0, 0.5), (1_000, 2.0), (10_000, 2.0), (316.23, 1.5)])
def test_value_weight_stops_dust_from_farming_trust(usd, v):
    assert value_weight(usd) == pytest.approx(v, abs=1e-3)


# --- new profiles -------------------------------------------------------------------------------


@pytest.mark.parametrize("tier", list(RiskTier))
def test_new_profile_starts_at_the_tier_defaults(tier):
    p = new_profile("0x" + "ab" * 20, tier)
    assert p.lam == LAMBDA_START[tier] and p.tau == 0.6 and p.approvals == {}
    lo, hi = LAMBDA_BANDS[tier]
    assert lo <= p.lam <= hi


def test_demo_profile_still_loads_with_the_new_fields():
    p = load_demo_profile()
    assert p.history == [] and p.seen_events == []


# --- each signal --------------------------------------------------------------------------------


def test_ratify_raises_approval_and_trust():
    r = learn(new_profile("u", RiskTier.BALANCED), event(Signal.RATIFY))
    assert r.applied
    assert r.profile.approvals[AAVE] == (3.0, 2.0)
    assert r.profile.tau == pytest.approx(0.62)
    assert any("trust" in c.lower() for c in r.changes)


def test_flag_is_a_heavy_penalty():
    r = learn(new_profile("u", RiskTier.BALANCED), event(Signal.FLAG))
    p = r.profile
    assert p.approvals[AAVE] == (2.0, 5.0)
    assert p.tau == pytest.approx(0.45)
    assert p.lam == pytest.approx(1.10)


def test_one_flag_costs_as_much_trust_as_seven_and_a_half_ratifies():
    ratify_gain = 0.02 * value_weight(100)
    flag_loss = 0.15
    assert flag_loss / ratify_gain == pytest.approx(7.5)


def test_note_with_penalty():
    p = learn(new_profile("u", RiskTier.BALANCED), event(Signal.NOTE_PENALTY)).profile
    assert p.approvals[AAVE] == (2.0, 3.5) and p.tau == pytest.approx(0.53) and p.lam == 1.0


def test_breakout_accept_and_reject():
    accept = learn(new_profile("u", RiskTier.BALANCED), event(Signal.BREAKOUT_ACCEPT)).profile
    assert accept.approvals[AAVE] == (3.0, 2.0) and accept.tau == pytest.approx(0.61)
    reject = learn(new_profile("u", RiskTier.BALANCED), event(Signal.BREAKOUT_REJECT)).profile
    assert reject.approvals[AAVE] == (2.0, 4.0) and reject.tau == pytest.approx(0.55)
    assert reject.lam == pytest.approx(1.05)


def test_breakout_without_a_venue_still_moves_trust():
    p = learn(new_profile("u", RiskTier.BALANCED), event(Signal.BREAKOUT_REJECT, venue=None)).profile
    assert p.approvals == {} and p.tau == pytest.approx(0.55)


def test_card_picks_move_loss_aversion_both_ways():
    safer = learn(new_profile("u", RiskTier.BALANCED), event(Signal.PICK_SAFER)).profile
    assert safer.lam == pytest.approx(1.05) and safer.approvals[AAVE] == (2.5, 2.0) and safer.tau == 0.6
    riskier = learn(new_profile("u", RiskTier.BALANCED), event(Signal.PICK_RISKIER)).profile
    assert riskier.lam == pytest.approx(0.95)


def test_ignored_proposal_changes_nothing_but_is_recorded():
    start = new_profile("u", RiskTier.BALANCED)
    r = learn(start, event(Signal.IGNORED))
    assert (r.profile.lam, r.profile.tau, r.profile.approvals) == (start.lam, start.tau, start.approvals)
    assert len(r.profile.history) == 1


def test_dust_ratify_counts_half():
    p = learn(new_profile("u", RiskTier.BALANCED), event(Signal.RATIFY, usd=1)).profile
    assert p.approvals[AAVE] == (2.5, 2.0) and p.tau == pytest.approx(0.61)


# --- safety rules -------------------------------------------------------------------------------


def test_trust_can_rise_at_most_five_points_a_day():
    p = run(new_profile("u", RiskTier.BALANCED), [event(Signal.RATIFY, n) for n in range(20)])
    assert p.tau == pytest.approx(0.65)
    assert p.approvals[AAVE][0] == pytest.approx(22.0)  # approval still learns; only trust is capped


def test_the_cap_resets_the_next_day():
    day1 = [event(Signal.RATIFY, n) for n in range(10)]
    day2 = [event(Signal.RATIFY, n, at=T0 + timedelta(days=1)) for n in range(10)]
    assert run(new_profile("u", RiskTier.BALANCED), day1 + day2).tau == pytest.approx(0.70)


def test_falls_are_never_capped():
    p = run(new_profile("u", RiskTier.BALANCED), [event(Signal.FLAG, n) for n in range(5)])
    assert p.tau == 0.0


def test_trust_never_exceeds_one():
    p = new_profile("u", RiskTier.BALANCED).model_copy(update={"tau": 0.99})
    assert learn(p, event(Signal.RATIFY, usd=10_000)).profile.tau == 1.0


@pytest.mark.parametrize("tier", list(RiskTier))
def test_loss_aversion_never_leaves_the_tier_band(tier):
    lo, hi = LAMBDA_BANDS[tier]
    flagged = run(new_profile("u", tier), [event(Signal.FLAG, n) for n in range(30)])
    assert flagged.lam == pytest.approx(hi)
    bold = run(new_profile("u", tier), [event(Signal.PICK_RISKIER, n) for n in range(80)])
    assert bold.lam == pytest.approx(lo, abs=0.01)  # ×0.95 approaches a 0.0 floor without reaching it


def test_old_feedback_fades_toward_the_prior_with_a_30_day_half_life():
    p = BrainProfile(account="u", tier=RiskTier.BALANCED, lam=1.0, approvals={AAVE: (5.0, 2.0)}, updated_at=T0)
    later = T0 + timedelta(days=30)
    r = learn(p, event(Signal.IGNORED, at=later))
    assert r.profile.approvals[AAVE] == pytest.approx((3.5, 2.0))
    assert APPROVAL_PRIOR == (2.0, 2.0)


def test_replaying_the_same_event_changes_nothing():
    once = learn(new_profile("u", RiskTier.BALANCED), event(Signal.RATIFY)).profile
    twice = learn(once, event(Signal.RATIFY))
    assert not twice.applied
    assert twice.profile == once


def test_learning_never_mutates_the_input():
    start = new_profile("u", RiskTier.BALANCED)
    snapshot = start.model_copy(deep=True)
    learn(start, event(Signal.FLAG))
    assert start == snapshot


def test_history_keeps_ninety_days():
    old = event(Signal.RATIFY, 1, at=T0 - timedelta(days=120))
    p = run(new_profile("u", RiskTier.BALANCED), [old, event(Signal.RATIFY, 2)])
    assert [e.event_id for e in p.history] == [event(Signal.RATIFY, 2).event_id]


def test_out_of_order_events_use_their_own_day_for_the_cap():
    late = [event(Signal.RATIFY, n, at=T0) for n in range(10)]
    early = [event(Signal.RATIFY, n, at=T0 - timedelta(days=1)) for n in range(10)]
    assert run(new_profile("u", RiskTier.BALANCED), late + early).tau == pytest.approx(0.70)


def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError):
        FeedbackEvent(event_id="x", signal=Signal.RATIFY, venue_id=AAVE, amount_usd=1, at=datetime(2026, 10, 16))

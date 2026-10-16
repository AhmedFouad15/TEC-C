import pytest

from tecc_brain.market import SnapshotSource
from tecc_brain.reference import load_reference
from tecc_brain.risk.regime import (
    assess_peg,
    fair_value,
    quiet_failure_floor,
    regime_probabilities,
)

REF = load_reference()
HURDLE = 0.0215


def _probs_for(episode):
    i = episode["inputs"]
    return regime_probabilities(
        gap=max(0.0, 1.0 - i["price"]),
        sentiment=i["sentiment_negative"],
        redemption=i["redemption_status"],
        quality=i["reserve_quality"],
        liquidity_stress=i["liquidity_stress"],
    )


# --- fair value ---------------------------------------------------------------------------------


def test_fair_value_haircuts_reserves_frozen_at_svb():
    assert fair_value(0.9175, 0.0, 1, HURDLE) == pytest.approx(0.91745, abs=1e-4)


def test_fair_value_is_par_with_full_coverage_and_instant_redemption():
    assert fair_value(1.0, 0.0, 0, HURDLE) == 1.0


def test_fair_value_deducts_redemption_fee():
    assert fair_value(1.0, 0.001, 0, HURDLE) == pytest.approx(0.999)


def test_fair_value_discounts_redemption_delay_at_the_hurdle_rate():
    assert fair_value(1.0, 0.0, 365, HURDLE) == pytest.approx(1 / 1.0215)


# --- regime probabilities -----------------------------------------------------------------------


@pytest.mark.parametrize("episode", REF.episodes, ids=lambda e: e["id"])
def test_reproduces_reference_episode(episode):
    probs = _probs_for(episode)
    expected = episode["expected"]

    assert probs.p_normal == pytest.approx(expected["p_normal"], abs=0.005)
    assert probs.p_distress == pytest.approx(expected["p_distress"], abs=0.005)
    assert probs.p_failure == pytest.approx(expected["p_failure"], abs=0.005)


@pytest.mark.parametrize(
    "episode_id, dominant",
    [
        ("usdc_svb_2023", "distress"),
        ("steth_celsius_2022", "distress"),
        ("ust_2022_collapse", "failure"),
        ("usdc_normal", "normal"),
    ],
)
def test_dominant_regime_matches_history(episode_id, dominant):
    assert _probs_for(REF.episode(episode_id)).dominant == dominant


def test_probabilities_sum_to_one():
    probs = regime_probabilities(gap=0.03, sentiment=0.4, redemption=0.5, quality=0.8, liquidity_stress=0.5)
    assert probs.p_normal + probs.p_distress + probs.p_failure == pytest.approx(1.0)


def test_contagion_raises_failure_probability():
    calm = regime_probabilities(gap=0.02, sentiment=0.3, redemption=0, quality=0.75, liquidity_stress=0.4)
    contagious = regime_probabilities(
        gap=0.02, sentiment=0.3, redemption=0, quality=0.75, liquidity_stress=0.4, contagion=0.5
    )
    assert contagious.p_failure > calm.p_failure


def test_distress_saturates_for_large_gaps_while_failure_keeps_rising():
    args = dict(sentiment=0.5, redemption=0.5, quality=0.5, liquidity_stress=0.5)
    at_cap = regime_probabilities(gap=0.08, **args)
    beyond = regime_probabilities(gap=0.30, **args)
    assert at_cap.z_distress == pytest.approx(beyond.z_distress)
    assert beyond.z_failure > at_cap.z_failure


def test_premium_above_peg_is_not_distress():
    above = regime_probabilities(gap=-0.01, sentiment=0.1, redemption=0, quality=0.95, liquidity_stress=0.05)
    at_peg = regime_probabilities(gap=0.0, sentiment=0.1, redemption=0, quality=0.95, liquidity_stress=0.05)
    assert above == at_peg


def test_quiet_failure_floor_for_high_quality_reserves():
    assert quiet_failure_floor(0.95) == pytest.approx(0.0011, abs=0.0002)


# --- assess_peg on market snapshots --------------------------------------------------------------


def test_assess_peg_flags_usdc_distress_in_svb_snapshot():
    snapshot = SnapshotSource("usdc_distress").snapshot()
    assessment = assess_peg(snapshot.pegs["USDC"], REF.assets["USDC"], snapshot.hurdle_rate)

    assert assessment.probs.dominant == "distress"
    assert assessment.fair_value == pytest.approx(0.9174, abs=1e-3)
    assert assessment.discount_to_fv == pytest.approx((0.9174 - 0.88) / 0.9174, abs=1e-3)


def test_assess_peg_on_a_normal_day_has_negligible_excess_failure():
    snapshot = SnapshotSource("demo").snapshot()
    assessment = assess_peg(snapshot.pegs["USDC"], REF.assets["USDC"], snapshot.hurdle_rate)

    assert assessment.probs.dominant == "normal"
    assert assessment.failure_excess < 0.001

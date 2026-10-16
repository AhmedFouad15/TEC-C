import pytest

from tecc_brain.market import SnapshotSource
from tecc_brain.reference import load_reference
from tecc_brain.risk.regime import assess_peg, regime_probabilities
from tecc_brain.risk.score import (
    entry_cost,
    recovery_edge,
    score_venue,
    stressed_exit_cost,
    venue_pd,
)

REF = load_reference()
HURDLE = 0.0215


def _assessments(snapshot):
    return {
        sym: assess_peg(peg, REF.assets[sym], snapshot.hurdle_rate)
        for sym, peg in snapshot.pegs.items()
    }


DEMO = SnapshotSource("demo").snapshot()
DEMO_ASSESSMENTS = _assessments(DEMO)


def _score(venue_id, lam=1.0, affinity=0.0, snapshot=DEMO, assessments=DEMO_ASSESSMENTS):
    venue = REF.venues[venue_id]
    return score_venue(venue, snapshot.venues[venue_id], snapshot, assessments, lam=lam, affinity=affinity)


# --- costs -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "venue_id, expected",
    [("lido_stake", 0.00099), ("curve_steth_eth", 0.0050), ("aave_v3_usdc", 0.0005), ("paxg_hold", 0.0020)],
)
def test_stressed_exit_cost_matches_spec(venue_id, expected):
    assert stressed_exit_cost(REF.venues[venue_id], HURDLE, 1.0) == pytest.approx(expected, abs=1e-5)


def test_entry_cost_is_annualised_over_the_horizon():
    paxg = REF.venues["paxg_hold"]
    assert entry_cost(paxg, 1.0) == pytest.approx(0.0003)
    assert entry_cost(paxg, 0.5) == pytest.approx(0.0006)


# --- probability of permanent impairment -------------------------------------------------------


def test_venue_pd_is_baseline_in_a_normal_market():
    aave = REF.venues["aave_v3_usdc"]
    assert venue_pd(aave, DEMO_ASSESSMENTS) == pytest.approx(aave.pd_base, abs=0.0005)


def test_venue_pd_without_exposures_is_baseline():
    mmf = REF.venues["shibor_mmf"]
    assert venue_pd(mmf, DEMO_ASSESSMENTS) == mmf.pd_base


def test_usdc_distress_raises_pd_of_usdc_venues():
    distress = SnapshotSource("usdc_distress").snapshot()
    aave = REF.venues["aave_v3_usdc"]
    assert venue_pd(aave, _assessments(distress)) > aave.pd_base + 0.005


# --- the demo table (BRAIN_DESIGN §2.2, Balanced λ = 1) -----------------------------------------


@pytest.mark.parametrize(
    "venue_id, expected",
    [("lido_stake", 0.0055), ("curve_steth_eth", 0.0300), ("aave_v3_usdc", 0.0160), ("paxg_hold", -0.0064)],
)
def test_demo_scores_match_the_pitch(venue_id, expected):
    assert _score(venue_id).total == pytest.approx(expected, abs=0.0003)


def test_curve_beats_lido_for_a_balanced_user():
    assert _score("curve_steth_eth").total > _score("lido_stake").total


def test_breakdown_terms_sum_to_total():
    s = _score("curve_steth_eth", affinity=0.5)
    assert s.excess_yield - s.loss_weighted - s.c_in - s.c_out_stress + s.affinity_term == pytest.approx(s.total)


def test_higher_loss_aversion_never_raises_a_score():
    for venue_id in DEMO.venues:
        assert _score(venue_id, lam=3.0).total <= _score(venue_id, lam=1.0).total


def test_affinity_moves_score_by_exactly_its_weight():
    assert _score("lido_stake", affinity=1.0).total - _score("lido_stake").total == pytest.approx(0.003)


# --- recovery-adjusted edge on de-pegged assets -------------------------------------------------


def _episode_edge(episode_id, costs):
    episode = REF.episode(episode_id)
    i = episode["inputs"]
    asset = REF.assets[episode["asset"]]
    from tecc_brain.models import PegState

    peg = PegState(
        symbol=asset.symbol,
        price=i["price"],
        sentiment_negative=i["sentiment_negative"],
        redemption_status=i["redemption_status"],
        liquidity_stress=i["liquidity_stress"],
        coverage=i["coverage"],
    )
    assessment = assess_peg(peg, asset.model_copy(update={"reserve_quality": i["reserve_quality"]}), HURDLE)
    return recovery_edge(i["price"], assessment, i["reserve_quality"], costs, HURDLE)


def test_buying_usdc_at_88_cents_is_positive_even_after_reserve_haircut():
    assert _episode_edge("usdc_svb_2023", costs=0.005) == pytest.approx(0.031, abs=0.002)


def test_buying_ust_at_95_cents_is_strongly_negative():
    assert _episode_edge("ust_2022_early", costs=0.01) == pytest.approx(-0.14, abs=0.003)


def test_edge_shrinks_as_failure_risk_grows():
    probs_low = regime_probabilities(gap=0.05, sentiment=0.3, redemption=0, quality=0.9, liquidity_stress=0.5)
    probs_high = regime_probabilities(gap=0.05, sentiment=0.9, redemption=1, quality=0.9, liquidity_stress=0.5)
    assert probs_high.p_failure > probs_low.p_failure

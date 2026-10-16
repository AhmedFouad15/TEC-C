from statistics import NormalDist

import pytest

from tecc_brain.market import SnapshotSource
from tecc_brain.models import ActionType, CardLabel, Mandate, VaultState
from tecc_brain.reference import load_reference
from tecc_brain.risk.metrics import CVAR_LEVEL, cvar, mixture_moments, risk_metrics, sharpe
from tecc_brain.risk.regime import assess_peg
from tecc_brain.risk.score import score_venue
from tecc_brain.strategy.planner import load_demo_profile, plan
from tecc_brain.strategy.portfolio import load_demo_portfolio

REF = load_reference()
DEMO = SnapshotSource("demo").snapshot()
DISTRESS = SnapshotSource("usdc_distress").snapshot()


def _scores(snapshot):
    assessments = {s: assess_peg(p, REF.assets[s], snapshot.hurdle_rate) for s, p in snapshot.pegs.items()}
    return {
        vid: score_venue(REF.venues[vid], q, snapshot, assessments, lam=1.0)
        for vid, q in snapshot.venues.items()
    }


# --- the maths ----------------------------------------------------------------------------------


def test_without_impairment_cvar_is_the_normal_tail():
    mu, sigma, alpha = 0.04, 0.02, 1 - CVAR_LEVEL
    z = NormalDist().inv_cdf(alpha)
    expected = sigma * NormalDist().pdf(z) / alpha - mu
    assert cvar(mu, sigma, pd=0.0, lgd=0.3) == pytest.approx(expected, abs=1e-6)


def test_a_likely_impairment_fills_the_whole_tail():
    assert cvar(0.04, 0.01, pd=0.10, lgd=0.40) == pytest.approx(0.40, abs=1e-6)


def test_impairment_partly_in_the_tail_is_weighted_by_its_mass():
    # 2% chance of losing 50%: the worst 5% = that 2% plus the worst 3% of normal years
    mu, sigma, pd, lgd, alpha = 0.05, 0.02, 0.02, 0.5, 0.05
    n = NormalDist()
    z = n.inv_cdf((alpha - pd) / (1 - pd))
    normal_part = (1 - pd) * (mu * n.cdf(z) - sigma * n.pdf(z))
    expected = -(pd * -lgd + normal_part) / alpha
    assert cvar(mu, sigma, pd, lgd) == pytest.approx(expected, abs=1e-6)


def test_mixture_moments():
    mean, sd = mixture_moments(0.05, 0.0, 0.5, 0.5)
    assert mean == pytest.approx(-0.225) and sd == pytest.approx(0.275)


def test_sharpe_is_excess_over_shibor_per_unit_of_volatility():
    assert sharpe(0.0415, 0.02, 0.0, 0.0, hurdle=0.0215) == pytest.approx(1.0)
    assert sharpe(0.03, 0.0, 0.0, 0.0, hurdle=0.02) is None  # riskless: ratio undefined


@pytest.mark.parametrize("pd_low, pd_high", [(0.001, 0.01), (0.01, 0.05)])
def test_more_impairment_risk_means_lower_sharpe_and_higher_cvar(pd_low, pd_high):
    low = risk_metrics(0.05, 0.02, pd_low, 0.3, hurdle=0.02)
    high = risk_metrics(0.05, 0.02, pd_high, 0.3, hurdle=0.02)
    assert high.sharpe < low.sharpe and high.cvar_95 > low.cvar_95


# --- on the demo data ---------------------------------------------------------------------------


def test_every_venue_has_a_volatility():
    assert all(v.vol_annual > 0 for v in REF.venues.values())


def test_every_score_carries_sharpe_and_cvar():
    for vid, s in _scores(DEMO).items():
        assert s.sharpe is not None and s.cvar_95 is not None, vid


def test_money_market_rail_has_the_smallest_tail():
    scores = _scores(DEMO)
    assert min(scores, key=lambda v: scores[v].cvar_95) == "shibor_mmf"


def test_usdc_distress_fattens_aaves_tail():
    assert _scores(DISTRESS)["aave_v3_usdc"].cvar_95 > _scores(DEMO)["aave_v3_usdc"].cvar_95


def test_metrics_never_change_the_decision_score():
    s = _scores(DEMO)["aave_v3_usdc"]
    assert s.total == pytest.approx(s.excess_yield - s.loss_weighted - s.c_in - s.c_out_stress + s.affinity_term)
    assert round(s.total * 100, 2) == 1.59


def test_cards_show_sharpe_and_cvar():
    mandate = Mandate(raw_text="Optimize my $1,500 USDC", action=ActionType.OPTIMIZE_YIELD, asset="USDC", amount=1500)
    decision = plan(mandate, DEMO, load_demo_portfolio(), load_demo_profile(), VaultState(tether_radius_usd=500), REF)
    best = next(c for c in decision.cards if c.label == CardLabel.BEST)
    assert any("Sharpe" in line and "CVaR" in line for line in best.explanation)

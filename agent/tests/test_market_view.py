import pytest

from tecc_brain.market import SnapshotSource
from tecc_brain.models import PegState
from tecc_brain.reference import load_reference
from tecc_brain.risk.regime import assess_peg
from tecc_brain.strategy.market_view import assess_market

REF = load_reference()
DEMO = SnapshotSource("demo").snapshot()
DISTRESS = SnapshotSource("usdc_distress").snapshot()


def _with_peg(snapshot, peg):
    return snapshot.model_copy(update={"pegs": {**snapshot.pegs, peg.symbol: peg}})


USDC_FAILING = PegState(
    symbol="USDC", price=0.70, sentiment_negative=0.9, redemption_status=1.0, liquidity_stress=0.9, coverage=0.9
)


def test_calm_market_has_no_stressed_cluster():
    view = assess_market(DEMO, REF)
    assert not any(status.stressed for status in view.clusters.values())
    assert all(k < 0.01 for status in view.clusters.values() for k in status.contagion_inputs.values())


def test_svb_style_shock_stresses_the_usd_cluster_without_failing_it():
    view = assess_market(DISTRESS, REF)
    usd = view.clusters["usd_fiat"]
    assert usd.stressed
    assert usd.failing == []


def test_dai_inherits_contagion_from_usdc_failure_risk():
    view = assess_market(DISTRESS, REF)
    usdc_alone = assess_peg(DISTRESS.pegs["USDC"], REF.assets["USDC"], DISTRESS.hurdle_rate)
    expected_k = 0.8 * usdc_alone.probs.p_failure
    assert view.clusters["usd_fiat"].contagion_inputs["DAI"] == pytest.approx(expected_k, abs=1e-9)


def test_a_failing_usdc_raises_dai_failure_risk():
    snapshot = _with_peg(DEMO, USDC_FAILING)
    view = assess_market(snapshot, REF)
    dai_alone = assess_peg(snapshot.pegs["DAI"], REF.assets["DAI"], snapshot.hurdle_rate)

    assert "USDC" in view.clusters["usd_fiat"].failing
    assert view.assessments["DAI"].probs.p_failure > dai_alone.probs.p_failure


def test_contagion_is_single_step_and_uses_standalone_failure():
    """A shocked target must not feed back into its source (no loops)."""
    snapshot = _with_peg(DEMO, USDC_FAILING)
    view = assess_market(snapshot, REF)
    usdc_alone = assess_peg(snapshot.pegs["USDC"], REF.assets["USDC"], snapshot.hurdle_rate)
    usdt_k = view.clusters["usd_fiat"].contagion_inputs["USDT"]
    assert usdt_k == pytest.approx(0.3 * usdc_alone.probs.p_failure, abs=1e-9)


def test_unknown_pegs_are_ignored():
    snapshot = _with_peg(DEMO, PegState(symbol="MYSTERY", price=0.5))
    view = assess_market(snapshot, REF)
    assert "MYSTERY" not in view.assessments

import pytest

from tecc_brain.market import SnapshotSource
from tecc_brain.models import RiskTier, VenueQuote
from tecc_brain.reference import load_reference
from tecc_brain.risk.filters import FilterContext, RejectReason, hard_filter_reasons, passes
from tecc_brain.risk.regime import PegAssessment, assess_peg, regime_probabilities

REF = load_reference()
DEMO = SnapshotSource("demo").snapshot()
DISTRESS = SnapshotSource("usdc_distress").snapshot()


def _assessments(snapshot):
    return {s: assess_peg(p, REF.assets[s], snapshot.hurdle_rate) for s, p in snapshot.pegs.items()}


DEMO_A = _assessments(DEMO)
BALANCED = FilterContext(tier=RiskTier.BALANCED)


def _reasons(venue_id, amount=400.0, ctx=BALANCED, snapshot=DEMO, assessments=DEMO_A, quote=None, edge=None):
    venue = REF.venues[venue_id]
    return hard_filter_reasons(
        venue, quote or snapshot.venues[venue_id], amount, assessments, ctx, edge=edge
    )


def test_clean_candidate_passes():
    assert _reasons("aave_v3_usdc") == []
    assert passes(REF.venues["aave_v3_usdc"], DEMO.venues["aave_v3_usdc"], 400.0, DEMO_A, BALANCED)


def test_tier_above_user_tier_is_rejected():
    assert _reasons("eigenlayer_restake") == [RejectReason.TIER_NOT_PERMITTED]


def test_aggressive_user_may_use_tier_3():
    assert _reasons("eigenlayer_restake", ctx=FilterContext(tier=RiskTier.AGGRESSIVE)) == []


def test_unwhitelisted_venue_is_rejected():
    ctx = FilterContext(tier=RiskTier.BALANCED, whitelist={"aave_v3_usdc"})
    assert _reasons("curve_steth_eth", ctx=ctx) == [RejectReason.NOT_WHITELISTED]


def test_tier_3_account_bypasses_whitelist_like_the_vault():
    ctx = FilterContext(tier=RiskTier.AGGRESSIVE, whitelist={"aave_v3_usdc"})
    assert _reasons("curve_steth_eth", ctx=ctx) == []


def _with_usdc_failure(p_failure_logit_boost):
    a = _assessments(DISTRESS)
    usdc = a["USDC"]
    probs = regime_probabilities(
        gap=usdc.gap, sentiment=0.85, redemption=1.0, quality=0.5, liquidity_stress=0.9, contagion=p_failure_logit_boost
    )
    a["USDC"] = usdc.model_copy(update={"probs": probs})
    return a


def test_failure_regime_vetoes_venues_exposed_to_it():
    assessments = _with_usdc_failure(1.0)
    assert assessments["USDC"].probs.p_failure >= 0.30
    reasons = _reasons("aave_v3_usdc", snapshot=DISTRESS, assessments=assessments)
    assert RejectReason.FAILURE_VETO in reasons


def test_temporary_distress_at_svb_levels_is_not_vetoed():
    assert RejectReason.FAILURE_VETO not in _reasons(
        "aave_v3_usdc", snapshot=DISTRESS, assessments=_assessments(DISTRESS)
    )


def test_bad_sentiment_alone_never_vetoes():
    a = dict(DEMO_A)
    probs = regime_probabilities(gap=0.0, sentiment=0.95, redemption=0, quality=0.95, liquidity_stress=0.05)
    a["USDC"] = PegAssessment(
        symbol="USDC", price=1.0, fair_value=1.0, gap=0.0, discount_to_fv=0.0, probs=probs, failure_excess=0.0
    )
    assert _reasons("aave_v3_usdc", assessments=a) == []


def test_non_positive_edge_is_rejected():
    assert _reasons("aave_v3_usdc", edge=-0.01) == [RejectReason.NEGATIVE_EDGE]
    assert _reasons("aave_v3_usdc", edge=0.0) == [RejectReason.NEGATIVE_EDGE]


def test_edge_is_ignored_when_not_provided():
    assert _reasons("aave_v3_usdc", edge=None) == []


def test_thin_pool_is_rejected():
    thin = VenueQuote(venue_id="aave_v3_usdc", apy=0.042, depth_usd=100_000)
    assert RejectReason.INSUFFICIENT_DEPTH in _reasons("aave_v3_usdc", amount=25_000, quote=thin)


def test_estimated_slippage_above_half_percent_is_rejected():
    shallow = VenueQuote(venue_id="aave_v3_usdc", apy=0.042, depth_usd=1_000_000)
    assert RejectReason.SLIPPAGE_TOO_HIGH in _reasons("aave_v3_usdc", amount=10_000, quote=shallow)


def test_stale_heartbeat_blocks_everything():
    ctx = FilterContext(tier=RiskTier.BALANCED, heartbeat_alive=False)
    assert RejectReason.HEARTBEAT_STALE in _reasons("aave_v3_usdc", ctx=ctx)


def test_multiple_reasons_come_back_in_a_stable_order():
    ctx = FilterContext(tier=RiskTier.BALANCED, whitelist=set(), heartbeat_alive=False)
    assert _reasons("eigenlayer_restake", ctx=ctx, edge=-1.0) == [
        RejectReason.HEARTBEAT_STALE,
        RejectReason.TIER_NOT_PERMITTED,
        RejectReason.NOT_WHITELISTED,
        RejectReason.NEGATIVE_EDGE,
    ]


@pytest.mark.parametrize("reason", list(RejectReason))
def test_every_reason_has_user_facing_text(reason):
    from tecc_brain.risk.filters import REASON_TEXT

    assert REASON_TEXT[reason].strip()

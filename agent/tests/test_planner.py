import pytest

from tecc_brain.market import SnapshotSource
from tecc_brain.models import (
    ActionType,
    AutonomyMode,
    BrainProfile,
    CardLabel,
    Mandate,
    RiskTier,
    VaultState,
)
from tecc_brain.reference import load_reference
from tecc_brain.strategy.planner import load_demo_profile, plan
from tecc_brain.strategy.portfolio import load_demo_portfolio

REF = load_reference()
DEMO = SnapshotSource("demo").snapshot()
DISTRESS = SnapshotSource("usdc_distress").snapshot()

SCENE_1 = Mandate(raw_text="Optimize my $1,500 USDC", action=ActionType.OPTIMIZE_YIELD, asset="USDC", amount=1500)
SCENE_3 = Mandate(raw_text="Stake my 10 ETH", action=ActionType.STAKE, asset="ETH", amount=10)


def _plan(mandate, *, snapshot=DEMO, profile=None, radius=500.0, **vault):
    return plan(
        mandate,
        snapshot,
        load_demo_portfolio(),
        profile or load_demo_profile(),
        VaultState(tether_radius_usd=radius, **vault),
        REF,
    )


def _card(decision, label):
    matches = [c for c in decision.cards if c.label == label]
    assert matches, f"no {label} card in {[c.label for c in decision.cards]}"
    return matches[0]


# --- profile model ------------------------------------------------------------------------------


def test_demo_profile_has_aave_history():
    profile = load_demo_profile()
    assert profile.tier == RiskTier.BALANCED
    assert profile.has_history("aave_v3_usdc") and not profile.has_history("curve_steth_eth")
    assert profile.approval_mean("aave_v3_usdc") == pytest.approx(5 / 7)
    assert profile.approval_mean("never_seen") == 0.5


def test_vault_state_remaining_radius():
    assert VaultState(tether_radius_usd=500, spent_today_usd=120).remaining_usd == 380
    assert VaultState(tether_radius_usd=500, spent_today_usd=900).remaining_usd == 0


# --- Scene 1: autonomous slice into Aave ---------------------------------------------------------


def test_scene_1_routes_400_into_aave_automatically():
    decision = _plan(SCENE_1)

    assert decision.mode == AutonomyMode.AUTO
    assert decision.auto_amount_usd == pytest.approx(400)
    assert decision.proposed_amount_usd == pytest.approx(1100)
    best = _card(decision, CardLabel.BEST)
    assert (best.candidate.venue_id, best.mode) == ("aave_v3_usdc", AutonomyMode.AUTO)


def test_scene_1_good_option_is_the_safe_harbour():
    assert _card(_plan(SCENE_1), CardLabel.GOOD).candidate.venue_id == "shibor_mmf"


def test_scene_1_rejects_tier_3_venues_with_reasons():
    rejected = {c.venue_id: c.rejected_reasons for c in _plan(SCENE_1).rejected}
    assert rejected["uniswap_v3_usdc_eth"] == ["TIER_NOT_PERMITTED"]


# --- Scene 3: proactive Curve recommendation behind FaceID ----------------------------------------


def test_scene_3_recommends_curve_over_lido_behind_faceid():
    decision = _plan(SCENE_3, radius=1000)

    assert decision.mode == AutonomyMode.PROPOSE
    assert decision.auto_amount_usd == 0
    good, best = _card(decision, CardLabel.GOOD), _card(decision, CardLabel.BEST)
    assert (good.candidate.venue_id, best.candidate.venue_id) == ("lido_stake", "curve_steth_eth")
    assert good.mode == best.mode == AutonomyMode.BREAKOUT
    assert any("+2.98%" in line for line in [best.headline, *best.explanation])


def test_every_scored_card_carries_its_breakdown():
    for card in _plan(SCENE_3, radius=1000).cards:
        assert card.candidate.score is not None
        assert card.candidate.score.total == pytest.approx(
            card.candidate.score.excess_yield
            - card.candidate.score.loss_weighted
            - card.candidate.score.c_in
            - card.candidate.score.c_out_stress
            + card.candidate.score.affinity_term
        )


# --- safety: when the Brain must not act alone ----------------------------------------------------


def test_new_user_never_gets_autonomous_execution():
    cold = BrainProfile(account="new", tier=RiskTier.BALANCED, lam=1.0)
    decision = _plan(SCENE_1, profile=cold)
    assert decision.mode == AutonomyMode.PROPOSE
    assert decision.auto_amount_usd == 0


def test_stressed_usd_cluster_stops_autonomy_and_offers_the_discount():
    decision = _plan(SCENE_1, snapshot=DISTRESS)
    assert decision.auto_amount_usd == 0
    assert decision.mode == AutonomyMode.PROPOSE
    assert any(c.label == CardLabel.OPPORTUNITY and c.candidate.asset_in == "USDC" for c in decision.cards)


def test_conservative_user_cannot_stake_into_tier_2():
    conservative = load_demo_profile().model_copy(update={"tier": RiskTier.CONSERVATIVE})
    decision = _plan(SCENE_3, profile=conservative, radius=1000)
    assert decision.mode == AutonomyMode.BLOCKED
    assert any("TIER_NOT_PERMITTED" in line for line in decision.trace)


def test_stale_heartbeat_blocks_everything():
    decision = _plan(SCENE_1, heartbeat_alive=False)
    assert decision.mode == AutonomyMode.BLOCKED
    assert decision.cards == []


def test_spent_radius_shrinks_the_autonomous_slice():
    decision = _plan(SCENE_1, spent_today_usd=300)
    assert decision.auto_amount_usd == pytest.approx(0.8 * 200)


def test_personal_history_shows_up_in_the_explanation():
    best = _card(_plan(SCENE_1), CardLabel.BEST)
    assert best.candidate.score.affinity_term > 0
    assert any("approved this protocol before" in line for line in best.explanation)


def test_opportunities_are_ranked_by_edge():
    edges = [c.candidate.apy for c in _plan(SCENE_1, snapshot=DISTRESS).cards if c.label == CardLabel.OPPORTUNITY]
    assert len(edges) >= 2 and edges == sorted(edges, reverse=True)

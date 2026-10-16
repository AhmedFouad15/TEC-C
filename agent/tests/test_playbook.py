import pytest

from tecc_brain.market import SnapshotSource
from tecc_brain.models import ActionType, AutonomyMode, CardLabel, PegState, Portfolio, Position, RiskTier
from tecc_brain.reference import load_reference
from tecc_brain.strategy.market_view import assess_market
from tecc_brain.strategy.playbook import Response, opportunity_cards, reduce_exposure_cards, respond
from tecc_brain.strategy.portfolio import portfolio_risk

REF = load_reference()
DEMO = SnapshotSource("demo").snapshot()
DISTRESS = SnapshotSource("usdc_distress").snapshot()


def _with_peg(snapshot, peg):
    return snapshot.model_copy(update={"pegs": {**snapshot.pegs, peg.symbol: peg}})


UST_COLLAPSE = PegState(symbol="UST", price=0.70, sentiment_negative=0.8, redemption_status=0.5, liquidity_stress=0.9)
UST_EARLY = PegState(symbol="UST", price=0.95, sentiment_negative=0.8, redemption_status=0.5, liquidity_stress=0.9)
STETH_FAILING = PegState(symbol="stETH", price=0.60, sentiment_negative=0.9, redemption_status=1.0, liquidity_stress=0.9)


def _view(snapshot):
    return assess_market(snapshot, REF)


# --- respond ------------------------------------------------------------------------------------


def test_normal_market_holds():
    assert respond(REF.assets["USDC"], _view(DEMO).assessments["USDC"]).response == Response.HOLD


def test_temporary_distress_holds_but_stops_new_deposits():
    entry = respond(REF.assets["USDC"], _view(DISTRESS).assessments["USDC"])
    assert entry.response == Response.HOLD_NO_NEW_DEPOSITS
    assert "redemption" in entry.rationale.lower()


def test_failing_stablecoin_exits_to_the_onshore_rail():
    view = _view(_with_peg(DEMO, UST_COLLAPSE))
    entry = respond(REF.assets["UST"], view.assessments["UST"])
    assert (entry.response, entry.destination) == (Response.EXIT, "shibor_mmf")


def test_failing_lst_unwinds_to_native_eth_not_a_short():
    view = _view(_with_peg(DEMO, STETH_FAILING))
    entry = respond(REF.assets["stETH"], view.assessments["stETH"])
    assert (entry.response, entry.destination) == (Response.EXIT, "ETH")


def test_algorithmic_stable_in_distress_is_exited():
    view = _view(_with_peg(DEMO, UST_EARLY))
    assert respond(REF.assets["UST"], view.assessments["UST"]).response == Response.EXIT


# --- reduce exposure ----------------------------------------------------------------------------


def _reduce(snapshot, positions, tier=RiskTier.BALANCED):
    view = _view(snapshot)
    portfolio = Portfolio(account="t", positions=positions)
    return reduce_exposure_cards(portfolio, view, portfolio_risk(portfolio, view, REF, tier), REF)


def test_position_in_a_failing_asset_is_fully_exited():
    [card] = _reduce(
        _with_peg(DEMO, UST_COLLAPSE),
        [Position(asset="UST", amount_usd=1_000), Position(asset="ETH", amount_usd=9_000)],
    )
    assert card.label == CardLabel.REDUCE_EXPOSURE
    assert (card.candidate.asset_in, card.candidate.amount_usd, card.candidate.venue_id) == ("UST", 1_000, "shibor_mmf")


def test_cap_breach_is_trimmed_to_the_cap():
    [card] = _reduce(DEMO, [Position(asset="USDC", amount_usd=1_500), Position(asset="ETH", amount_usd=500)])
    assert card.candidate.amount_usd == pytest.approx(500)
    assert card.candidate.action == ActionType.REDUCE_EXPOSURE


def test_temporary_distress_alone_never_triggers_selling():
    assert _reduce(DISTRESS, [Position(asset="USDC", amount_usd=1_000), Position(asset="ETH", amount_usd=9_000)]) == []


def test_venue_position_exit_names_the_venue_it_leaves():
    [card] = _reduce(
        _with_peg(DEMO, STETH_FAILING), [Position(asset="ETH", venue_id="lido_stake", amount_usd=5_000)]
    )
    assert (card.candidate.from_venue_id, card.candidate.venue_id) == ("lido_stake", "ETH")


# --- opportunities ------------------------------------------------------------------------------


def test_svb_style_discount_is_offered_as_a_proposal():
    cards = opportunity_cards(_view(DISTRESS), DISTRESS, REF, budget_usd=400)
    usdc = [c for c in cards if c.candidate.asset_in == "USDC"]
    assert len(usdc) == 1
    card = usdc[0]
    assert card.label == CardLabel.OPPORTUNITY and card.mode == AutonomyMode.PROPOSE
    assert card.candidate.action == ActionType.BUY_DISCOUNT and card.candidate.amount_usd == 400
    assert 0.02 < card.candidate.apy < 0.04  # recovery-adjusted edge carried in apy slot
    assert any("%" in line for line in card.explanation)


def test_calm_market_has_no_opportunities():
    assert opportunity_cards(_view(DEMO), DEMO, REF, budget_usd=400) == []


def test_negative_edge_discount_is_not_offered():
    snapshot = _with_peg(DEMO, UST_EARLY)
    assert [c for c in opportunity_cards(_view(snapshot), snapshot, REF, 400) if c.candidate.asset_in == "UST"] == []


def test_no_shorts_or_delta_neutral_hedges_anywhere():
    allowed = {ActionType.DEPOSIT, ActionType.STAKE, ActionType.REDUCE_EXPOSURE, ActionType.BUY_DISCOUNT, ActionType.WITHDRAW}
    cards = [
        *opportunity_cards(_view(DISTRESS), DISTRESS, REF, 400),
        *_reduce(_with_peg(DEMO, UST_COLLAPSE), [Position(asset="UST", amount_usd=1_000)]),
        *_reduce(_with_peg(DEMO, STETH_FAILING), [Position(asset="stETH", amount_usd=1_000)]),
    ]
    assert cards and {c.candidate.action for c in cards} <= allowed

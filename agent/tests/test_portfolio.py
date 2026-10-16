import pytest

from tecc_brain.market import SnapshotSource
from tecc_brain.models import Portfolio, Position, RiskTier
from tecc_brain.reference import load_reference
from tecc_brain.strategy.market_view import assess_market
from tecc_brain.strategy.portfolio import CLUSTER_CAPS, load_demo_portfolio, portfolio_risk

REF = load_reference()
DEMO_VIEW = assess_market(SnapshotSource("demo").snapshot(), REF)


def test_cluster_caps_tighten_with_risk_appetite():
    assert CLUSTER_CAPS[RiskTier.CONSERVATIVE] > CLUSTER_CAPS[RiskTier.BALANCED] > CLUSTER_CAPS[RiskTier.AGGRESSIVE]


def test_demo_portfolio_has_no_breach():
    portfolio = load_demo_portfolio()
    risk = portfolio_risk(portfolio, DEMO_VIEW, REF, RiskTier.BALANCED)
    assert portfolio.nav_usd == 26_500
    assert risk.cap_breaches == []


def test_expected_loss_matches_hand_calculation():
    portfolio = load_demo_portfolio()
    risk = portfolio_risk(portfolio, DEMO_VIEW, REF, RiskTier.BALANCED)

    usdc = REF.assets["USDC"]
    usdc_pd = 1 - (1 - usdc.pd_base) * (1 - DEMO_VIEW.assessments["USDC"].failure_excess)
    expected = 1_500 * usdc_pd * usdc.lgd  # ETH: no pd_base, no lgd
    assert risk.expected_loss_usd == pytest.approx(expected, abs=1e-6)
    assert risk.expected_loss_fraction == pytest.approx(expected / 26_500)


def test_venue_positions_use_venue_risk():
    portfolio = Portfolio(account="t", positions=[Position(asset="USDC", venue_id="aave_v3_usdc", amount_usd=1_000)])
    risk = portfolio_risk(portfolio, DEMO_VIEW, REF, RiskTier.BALANCED)
    aave = REF.venues["aave_v3_usdc"]
    assert risk.expected_loss_usd == pytest.approx(1_000 * aave.pd_base * aave.lgd, rel=0.05)
    assert risk.cluster_exposure_usd["usd_fiat"] == 1_000


def test_stablecoin_heavy_balanced_portfolio_breaches_the_cluster_cap():
    portfolio = Portfolio(
        account="t",
        positions=[Position(asset="USDC", amount_usd=1_500), Position(asset="ETH", amount_usd=500)],
    )
    risk = portfolio_risk(portfolio, DEMO_VIEW, REF, RiskTier.BALANCED)

    assert risk.cluster_share["usd_fiat"] == pytest.approx(0.75)
    [breach] = risk.cap_breaches
    assert (breach.cluster, breach.cap, breach.excess_usd) == ("usd_fiat", 0.50, pytest.approx(500))


def test_non_stablecoin_clusters_are_not_capped():
    portfolio = Portfolio(account="t", positions=[Position(asset="stETH", amount_usd=10_000)])
    risk = portfolio_risk(portfolio, DEMO_VIEW, REF, RiskTier.BALANCED)
    assert risk.cluster_share["eth_lst"] == 1.0
    assert risk.cap_breaches == []


def test_empty_portfolio_is_safe():
    risk = portfolio_risk(Portfolio(account="t", positions=[]), DEMO_VIEW, REF, RiskTier.BALANCED)
    assert (risk.nav_usd, risk.expected_loss_fraction, risk.cap_breaches) == (0, 0, [])

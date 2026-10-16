"""Portfolio-level risk: cluster exposure vs tier caps and contagion-adjusted expected loss (BRAIN_DESIGN §2.5)."""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel

from tecc_brain.models import Portfolio, Position, RiskTier
from tecc_brain.reference import Reference, read_data_json
from tecc_brain.risk.score import venue_pd
from tecc_brain.strategy.market_view import MarketView

# Max share of NAV in one stablecoin cluster. Tighter for aggressive users: their other holdings are volatile,
# so a stablecoin cluster failing hits them when they have the least liquid cushion.
CLUSTER_CAPS: dict[RiskTier, float] = {
    RiskTier.CONSERVATIVE: 0.60,
    RiskTier.BALANCED: 0.50,
    RiskTier.AGGRESSIVE: 0.40,
}
STABLECOIN_CLUSTERS = frozenset({"usd_fiat", "usd_algo"})


class CapBreach(BaseModel):
    cluster: str
    share: float
    cap: float
    excess_usd: float


class PortfolioRisk(BaseModel):
    nav_usd: float
    cluster_exposure_usd: dict[str, float]
    cluster_share: dict[str, float]
    expected_loss_usd: float
    expected_loss_fraction: float
    cap_breaches: list[CapBreach]


def position_exposures(position: Position, ref: Reference) -> list[str]:
    if position.venue_id:
        return list(ref.venues[position.venue_id].exposures)
    asset = ref.assets.get(position.asset)
    return [position.asset] if asset and asset.peg else []


def position_expected_loss(position: Position, view: MarketView, ref: Reference) -> float:
    """Annual expected permanent loss in USD for one position."""
    if position.venue_id:
        venue = ref.venues[position.venue_id]
        return position.amount_usd * venue_pd(venue, view.assessments) * venue.lgd
    asset = ref.assets[position.asset]
    excess = view.assessments[asset.symbol].failure_excess if asset.symbol in view.assessments else 0.0
    pd = 1.0 - (1.0 - asset.pd_base) * (1.0 - excess)
    return position.amount_usd * pd * asset.lgd


def portfolio_risk(portfolio: Portfolio, view: MarketView, ref: Reference, tier: RiskTier) -> PortfolioRisk:
    nav = portfolio.nav_usd
    exposure: dict[str, float] = defaultdict(float)
    for position in portfolio.positions:
        clusters = {ref.assets[s].cluster for s in position_exposures(position, ref) if ref.assets[s].cluster}
        for cluster in clusters:
            exposure[cluster] += position.amount_usd

    share = {c: (usd / nav if nav else 0.0) for c, usd in exposure.items()}
    cap = CLUSTER_CAPS[tier]
    breaches = [
        CapBreach(cluster=c, share=share[c], cap=cap, excess_usd=exposure[c] - cap * nav)
        for c in sorted(exposure)
        if c in STABLECOIN_CLUSTERS and share[c] > cap
    ]
    expected_loss = sum(position_expected_loss(p, view, ref) for p in portfolio.positions)
    return PortfolioRisk(
        nav_usd=nav,
        cluster_exposure_usd=dict(exposure),
        cluster_share=share,
        expected_loss_usd=expected_loss,
        expected_loss_fraction=expected_loss / nav if nav else 0.0,
        cap_breaches=breaches,
    )


def load_demo_portfolio() -> Portfolio:
    return Portfolio.model_validate(read_data_json("portfolio_demo.json"))

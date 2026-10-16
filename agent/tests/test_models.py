from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from tecc_brain.models import (
    Asset,
    AssetKind,
    MarketSnapshot,
    PegState,
    RiskTier,
    VenueQuote,
    onchain_to_usd,
    usd_to_onchain,
)


def test_risk_tiers_match_vault_constants():
    assert [RiskTier.CONSERVATIVE, RiskTier.BALANCED, RiskTier.AGGRESSIVE] == [1, 2, 3]


def test_asset_rejects_reserve_quality_above_one():
    with pytest.raises(ValidationError):
        Asset(symbol="X", name="X", kind=AssetKind.STABLE_FIAT, tier=1, reserve_quality=1.2)


def test_asset_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        Asset(symbol="X", name="X", kind=AssetKind.STABLE_FIAT, tier=1, surprise=True)


def test_peg_state_rejects_unknown_redemption_status():
    with pytest.raises(ValidationError):
        PegState(symbol="USDC", price=0.99, redemption_status=0.3)


def test_peg_state_accepts_paused_redemptions():
    assert PegState(symbol="USDC", price=0.88, redemption_status=1.0).redemption_status == 1.0


def test_tether_radius_converts_to_8_decimal_usd():
    assert usd_to_onchain(500.0) == 50_000_000_000
    assert onchain_to_usd(50_000_000_000) == 500.0


def test_onchain_conversion_round_trips_cents():
    assert onchain_to_usd(usd_to_onchain(1234.56)) == 1234.56


def test_market_snapshot_round_trips_through_json():
    snapshot = MarketSnapshot(
        as_of=datetime(2026, 10, 16, tzinfo=timezone.utc),
        hurdle_rate=0.0215,
        shibor={"1Y": 0.0215},
        venues={"aave_v3_usdc": VenueQuote(venue_id="aave_v3_usdc", apy=0.042, depth_usd=1e9)},
        pegs={"USDC": PegState(symbol="USDC", price=0.999)},
        source="test",
    )

    assert MarketSnapshot.model_validate_json(snapshot.model_dump_json()) == snapshot

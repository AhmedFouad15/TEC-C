"""Unit tests for live market data feed and catalog."""

from unittest.mock import MagicMock, patch

from tecc_brain.market.live_feed import (
    FREE_DATA_FEEDS,
    LiveMarketDataSource,
    PAID_ENTERPRISE_FEEDS,
)
from tecc_brain.models import MarketSnapshot


def test_free_and_paid_feed_catalogs():
    assert "chainlink_rpc" in FREE_DATA_FEEDS
    assert "defillama" in FREE_DATA_FEEDS
    assert "binance_public" in FREE_DATA_FEEDS
    assert "alternative_me" in FREE_DATA_FEEDS

    assert FREE_DATA_FEEDS["chainlink_rpc"]["requires_key"] is False
    assert FREE_DATA_FEEDS["defillama"]["requires_key"] is False
    assert FREE_DATA_FEEDS["binance_public"]["requires_key"] is False

    assert "bloomberg" in PAID_ENTERPRISE_FEEDS
    assert "kaiko" in PAID_ENTERPRISE_FEEDS
    assert "amberdata" in PAID_ENTERPRISE_FEEDS
    assert "coinapi" in PAID_ENTERPRISE_FEEDS
    assert "nansen" in PAID_ENTERPRISE_FEEDS

    assert PAID_ENTERPRISE_FEEDS["bloomberg"]["requires_key"] is True
    assert PAID_ENTERPRISE_FEEDS["kaiko"]["requires_key"] is True


def test_live_market_data_source_offline_fallback():
    source = LiveMarketDataSource(fallback_snapshot="demo")

    # When all remote calls fail, gracefully falls back to bundled demo snapshot
    with patch.object(source, "_fetch_chainlink_prices", return_value={}):
        with patch.object(source, "_fetch_defillama_prices", return_value={}):
            with patch.object(source, "_fetch_binance_prices", return_value={}):
                snap = source.snapshot()
                assert isinstance(snap, MarketSnapshot)
                assert "fallback:snapshot" in snap.source
                assert snap.prices_usd["ETH"] > 0
                assert "stETH" in snap.pegs


def test_live_market_data_source_with_chainlink_and_defillama():
    source = LiveMarketDataSource(fallback_snapshot="demo", cache_ttl_seconds=30.0)

    mock_cl = {"ETH": 2750.0, "WBTC": 85000.0, "USDC": 1.0, "PAXG": 2700.0}
    mock_dl = {"stETH": 2745.0, "DAI": 1.0}

    with patch.object(source, "_fetch_chainlink_prices", return_value=mock_cl):
        with patch.object(source, "_fetch_defillama_prices", return_value=mock_dl):
            snap = source.snapshot()
            assert isinstance(snap, MarketSnapshot)
            assert "chainlink" in snap.source
            assert "defillama" in snap.source
            assert snap.prices_usd["ETH"] == 2750.0
            assert snap.prices_usd["WBTC"] == 85000.0
            assert snap.prices_usd["stETH"] == 2745.0
            # stETH peg ratio updated: 2745 / 2750 = 0.99818
            assert abs(snap.pegs["stETH"].price - (2745.0 / 2750.0)) < 1e-4

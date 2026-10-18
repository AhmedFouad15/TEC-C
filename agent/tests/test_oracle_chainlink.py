"""Unit tests for Chainlink On-Chain Price Feed Oracle client."""

import pytest
from unittest.mock import patch, MagicMock

from eth_abi import encode

from tecc_brain.onchain.oracle import (
    ChainlinkOracleClient,
    ChainlinkRoundData,
    get_chainlink_oracle,
    FEEDS_FILE,
)


def test_feeds_file_exists_and_contains_expected_chains():
    client = ChainlinkOracleClient(config_file=FEEDS_FILE)
    assert 1 in [c.chainId for c in client._networks.values()]
    assert 42161 in [c.chainId for c in client._networks.values()]
    assert 11155111 in [c.chainId for c in client._networks.values()]


def test_get_feed_address_resolution():
    client = ChainlinkOracleClient(config_file=FEEDS_FILE)
    eth_mainnet = client.get_feed_address("ETH", chain_id=1)
    assert eth_mainnet == "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419"

    eth_arbitrum = client.get_feed_address("ETH", chain_id=42161)
    assert eth_arbitrum == "0x639Fe6ab55C921f74e7fac1ee960C0B6293ba612"

    btc_arbitrum = client.get_feed_address("BTC", chain_id=42161)
    assert btc_arbitrum == "0x6ce185860a4963106506C203335A2910413708e9"

    unknown = client.get_feed_address("NONEXISTENT_TOKEN", chain_id=1)
    assert unknown is None


def test_decode_round_data_validation():
    client = ChainlinkOracleClient(config_file=FEEDS_FILE)

    # Mock valid round data: roundId=10, answer=2500_00000000 ($2,500), updatedAt=1000, answeredInRound=10
    raw_bytes = encode(
        ["uint80", "int256", "uint256", "uint256", "uint80"],
        [10, 250000000000, 1000, 1000, 10],
    )
    mock_resp = MagicMock()
    mock_resp.read.return_value = f'{{"jsonrpc":"2.0","id":1,"result":"0x{raw_bytes.hex()}"}}'.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        data = client.fetch_round_data("ETH", chain_id=1, rpc_url="http://fake-rpc")
        assert data.symbol == "ETH"
        assert data.price_usd == 2500.0
        assert data.raw_answer == 250000000000
        assert data.round_id == 10
        assert data.decimals == 8


def test_decode_round_data_rejects_negative_or_zero_price():
    client = ChainlinkOracleClient(config_file=FEEDS_FILE)

    # answer = -1
    raw_bytes = encode(
        ["uint80", "int256", "uint256", "uint256", "uint80"],
        [10, -1, 1000, 1000, 10],
    )
    mock_resp = MagicMock()
    mock_resp.read.return_value = f'{{"jsonrpc":"2.0","id":1,"result":"0x{raw_bytes.hex()}"}}'.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(ValueError, match="non-positive price"):
            client.fetch_round_data("ETH", chain_id=1, rpc_url="http://fake-rpc")


def test_decode_round_data_rejects_incomplete_round():
    client = ChainlinkOracleClient(config_file=FEEDS_FILE)

    # answeredInRound < roundId
    raw_bytes = encode(
        ["uint80", "int256", "uint256", "uint256", "uint80"],
        [10, 250000000000, 1000, 1000, 9],
    )
    mock_resp = MagicMock()
    mock_resp.read.return_value = f'{{"jsonrpc":"2.0","id":1,"result":"0x{raw_bytes.hex()}"}}'.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(ValueError, match="Incomplete round"):
            client.fetch_round_data("ETH", chain_id=1, rpc_url="http://fake-rpc")


def test_client_caching():
    client = ChainlinkOracleClient(config_file=FEEDS_FILE, cache_ttl_seconds=60.0)
    raw_bytes = encode(
        ["uint80", "int256", "uint256", "uint256", "uint80"],
        [1, 260000000000, 1000, 1000, 1],
    )
    mock_resp = MagicMock()
    mock_resp.read.return_value = f'{{"jsonrpc":"2.0","id":1,"result":"0x{raw_bytes.hex()}"}}'.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_url:
        p1 = client.fetch_round_data("ETH", chain_id=1, rpc_url="http://fake-rpc")
        p2 = client.fetch_round_data("ETH", chain_id=1, rpc_url="http://fake-rpc")
        assert p1.price_usd == p2.price_usd
        assert mock_url.call_count == 1  # Second call served from cache

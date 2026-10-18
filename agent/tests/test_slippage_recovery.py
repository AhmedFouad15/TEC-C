"""Unit tests for Market Microstructure Resilience: Slippage Exceeded Halved Recovery (Q*/2)."""

from unittest.mock import MagicMock, patch
import pytest

from tecc_brain.models import ActionType, CardLabel, ExecutionIntent, usd_to_onchain
from tecc_brain.onchain.deploy import LocalDeployment
from tecc_brain.onchain.executor import ChainExecutor
from tecc_brain.onchain.mandate import UserMandate
from tecc_brain.onchain.rpc import RpcError


@pytest.fixture
def mock_executor():
    mock_rpc = MagicMock()
    mock_rpc.chain_id.return_value = 1337
    mock_rpc.call.return_value = "0x1"
    mock_rpc.fee_fields.return_value = {"maxFeePerGas": 10**9, "maxPriorityFeePerGas": 10**8}

    dep = LocalDeployment(
        chain_id=1337,
        root_owner="0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        hook="0x1111111111111111111111111111111111111111",
        validator="0x2222222222222222222222222222222222222222",
        account="0x3333333333333333333333333333333333333333",
        usdc="0x4444444444444444444444444444444444444444",
        eth_feed="0x5555555555555555555555555555555555555555",
        usdc_feed="0x6666666666666666666666666666666666666666",
        venues={"uniswap_v3_usdc_eth": "0x7777777777777777777777777777777777777777"},
        eth_usd=2500.0,
        deployed_block=1,
    )
    mandate = UserMandate(
        account=dep.account,
        session_key="0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        max_amount_usd=1000.0,
        valid_after=0,
        valid_until=2000000000,
        risk_tier=2,
        policy="0x" + "00" * 32,
    )
    key = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
    executor = ChainExecutor(mock_rpc, dep, key, mandate)
    return executor


def test_is_slippage_error():
    assert ChainExecutor._is_slippage_error("execution reverted: SLIPPAGE_EXCEEDED")
    assert ChainExecutor._is_slippage_error("UniswapV2: INSUFFICIENT_OUTPUT_AMOUNT")
    assert ChainExecutor._is_slippage_error("revert: Too little received from swap")
    assert ChainExecutor._is_slippage_error("price_impact_too_high")
    assert not ChainExecutor._is_slippage_error("execution reverted: TETHER_RADIUS_EXCEEDED")
    assert not ChainExecutor._is_slippage_error("unauthorized target")


def test_slippage_exceeded_halved_recovery_succeeds(mock_executor):
    intent = ExecutionIntent(
        card_label=CardLabel.BETTER,
        venue_id="uniswap_v3_usdc_eth",
        action=ActionType.SWAP,
        asset_in="USDC",
        amount_usd=100.0,
        amount_onchain=usd_to_onchain(100.0),
    )

    # First attempt: eth_call raises RpcError with SLIPPAGE_EXCEEDED
    # Second attempt (halved to 50.0): eth_call succeeds and send_raw succeeds
    calls = []

    def mock_eth_call(method, params):
        if method == "eth_call":
            calls.append(params)
            if len(calls) == 1:
                raise RpcError(-32000, "execution reverted: SLIPPAGE_EXCEEDED")
            return "0x"
        if method == "eth_estimateGas":
            return "0x5208"
        if method == "eth_getTransactionCount":
            return "0x0"
        return "0x1"

    mock_executor.rpc.call = mock_eth_call
    mock_executor.rpc.send_raw.return_value = {
        "transactionHash": "0xabc123456789",
        "logs": [],
    }

    with patch.object(mock_executor.validator, "call", return_value=[bytes.fromhex("1626ba7e")]):
        result = mock_executor.submit(intent, mock_executor.dep.account)

    assert result.status == "submitted"
    assert result.tx_hash == "0xabc123456789"
    assert result.amount_usd == 50.0  # halved order size Q*/2
    assert "Slippage exceeded on $100.00 order" in result.detail
    assert "E[ΔV]=+$0.25" in result.detail  # positive carry verified


def test_slippage_exceeded_halved_recovery_does_not_loop(mock_executor):
    intent = ExecutionIntent(
        card_label=CardLabel.BETTER,
        venue_id="uniswap_v3_usdc_eth",
        action=ActionType.SWAP,
        asset_in="USDC",
        amount_usd=100.0,
        amount_onchain=usd_to_onchain(100.0),
    )

    # Both attempts fail with SLIPPAGE_EXCEEDED
    def mock_eth_call(method, params):
        raise RpcError(-32000, "execution reverted: SLIPPAGE_EXCEEDED")

    mock_executor.rpc.call = mock_eth_call

    with patch.object(mock_executor.validator, "call", return_value=[bytes.fromhex("1626ba7e")]):
        result = mock_executor.submit(intent, mock_executor.dep.account)

    assert result.status == "failed"
    assert "refused by the vault: execution reverted: SLIPPAGE_EXCEEDED" in result.detail
    assert result.amount_usd == 50.0  # Halved once, then stopped cleanly


def test_non_slippage_revert_does_not_retry_halving(mock_executor):
    intent = ExecutionIntent(
        card_label=CardLabel.BETTER,
        venue_id="uniswap_v3_usdc_eth",
        action=ActionType.SWAP,
        asset_in="USDC",
        amount_usd=100.0,
        amount_onchain=usd_to_onchain(100.0),
    )

    mock_executor.rpc.call.side_effect = RpcError(-32000, "execution reverted: TETHER_RADIUS_EXCEEDED")

    with patch.object(mock_executor.validator, "call", return_value=[bytes.fromhex("1626ba7e")]):
        result = mock_executor.submit(intent, mock_executor.dep.account)

    assert result.status == "failed"
    assert result.amount_usd == 100.0  # Original amount unchanged
    assert "TETHER_RADIUS_EXCEEDED" in result.detail

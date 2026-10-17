import os
import pytest
from unittest.mock import MagicMock

from tecc_brain.onchain.network import (
    ARBITRUM_CONTRACTS_FILE,
    FISCO_CONTRACTS_FILE,
    SEPOLIA_CONTRACTS_FILE,
    NetworkConfigError,
    current_network,
    load_arbitrum_deployment,
    load_fisco_deployment,
    make_deployment,
    rpc_url_for,
)


def test_current_network_selection(monkeypatch):
    monkeypatch.setenv("TECC_NETWORK", "anvil")
    assert current_network() == "anvil"

    monkeypatch.setenv("TECC_NETWORK", "sepolia")
    assert current_network() == "sepolia"

    monkeypatch.setenv("TECC_NETWORK", "arbitrum")
    assert current_network() == "arbitrum"

    monkeypatch.setenv("TECC_NETWORK", "fisco_bcos")
    assert current_network() == "fisco_bcos"

    monkeypatch.setenv("TECC_NETWORK", "unsupported_net")
    with pytest.raises(NetworkConfigError):
        current_network()


def test_rpc_url_for_multi_chain(monkeypatch):
    # Anvil default
    monkeypatch.delenv("TECC_ANVIL_RPC_URL", raising=False)
    assert rpc_url_for("anvil") == "http://127.0.0.1:8545"

    # Arbitrum One
    monkeypatch.setenv("ARBITRUM_RPC_URL", "https://arb1.arbitrum.io/rpc")
    assert rpc_url_for("arbitrum") == "https://arb1.arbitrum.io/rpc"

    # FISCO BCOS
    monkeypatch.setenv("FISCO_BCOS_RPC_URL", "http://127.0.0.1:20200")
    assert rpc_url_for("fisco_bcos") == "http://127.0.0.1:20200"

    # Invalid scheme
    monkeypatch.setenv("SEPOLIA_RPC_URL", "ftp://some.node")
    with pytest.raises(NetworkConfigError):
        rpc_url_for("sepolia")


def test_shared_contract_configs_exist():
    assert SEPOLIA_CONTRACTS_FILE.exists()
    assert ARBITRUM_CONTRACTS_FILE.exists()
    assert FISCO_CONTRACTS_FILE.exists()


def test_load_arbitrum_and_fisco_deployments():
    mock_rpc = MagicMock()
    mock_rpc.call.return_value = "0x100"

    # In production without live deploys, DEAD_ADDRESS in deployedAddresses will raise _require_deployed
    # verifying that undeployed safety checks are actively enforced
    with pytest.raises(NetworkConfigError) as exc_arb:
        load_arbitrum_deployment(mock_rpc)
    assert "Arbitrum" in str(exc_arb.value)

    with pytest.raises(NetworkConfigError) as exc_fisco:
        load_fisco_deployment(mock_rpc)
    assert "FISCO BCOS" in str(exc_fisco.value)

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

    # FISCO BCOS (defaults to 127.0.0.1:8555 if not set)
    monkeypatch.delenv("FISCO_BCOS_RPC_URL", raising=False)
    assert rpc_url_for("fisco_bcos") == "http://127.0.0.1:8555"
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


def test_load_arbitrum_and_fisco_deployments(tmp_path):
    mock_rpc = MagicMock()
    mock_rpc.call.return_value = "0x100"

    # Arbitrum without live deploys has DEAD_ADDRESS, raising NetworkConfigError
    with pytest.raises(NetworkConfigError) as exc_arb:
        load_arbitrum_deployment(mock_rpc)
    assert "Arbitrum" in str(exc_arb.value)

    # FISCO BCOS has live testnet deployment loaded from shared/contracts.fisco.json
    fisco_deploy = load_fisco_deployment(mock_rpc)
    assert fisco_deploy.chain_id == 20200
    assert fisco_deploy.hook.startswith("0x")
    assert fisco_deploy.validator.startswith("0x")
    assert fisco_deploy.account.startswith("0x")

    # When missing or dead addresses are encountered, safety checks raise NetworkConfigError
    dead_fisco = tmp_path / "dead.json"
    dead_fisco.write_text(
        '{"_meta": {"chainId": 20200}, "deployedAddresses": {"TetherGuardHook": "0x000000000000000000000000000000000000dEaD"}}'
    )
    with pytest.raises(NetworkConfigError) as exc_fisco_dead:
        load_fisco_deployment(mock_rpc, path=dead_fisco)
    assert "FISCO BCOS" in str(exc_fisco_dead.value)

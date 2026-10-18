"""Unit tests for DeFi Protocols Registry."""

import pytest

from tecc_brain.data.defi_registry import (
    DefiRegistry,
    get_defi_registry,
    DEFI_PROTOCOLS_FILE,
)


def test_registry_file_exists_and_loads():
    reg = get_defi_registry()
    protocols = reg.list_all()
    assert len(protocols) >= 5
    pids = [p.id for p in protocols]
    assert "lido" in pids
    assert "curve" in pids
    assert "aave_v3" in pids
    assert "uniswap_v3" in pids
    assert "compound_v3" in pids


def test_lido_protocol_details():
    reg = get_defi_registry()
    lido = reg.get("lido")
    assert lido is not None
    assert lido.riskTier == 1
    assert "1" in lido.chains
    eth = lido.chains["1"]
    assert eth.contracts["stETH"] == "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84"
    interaction = eth.interactions["stake"]
    assert interaction.selector == "0xa1903eab"
    assert interaction.isPayable is True


def test_curve_protocol_details():
    reg = get_defi_registry()
    curve = reg.get("curve")
    assert curve is not None
    assert curve.riskTier == 2
    assert "1" in curve.chains
    assert "42161" in curve.chains
    interaction = curve.get_interaction("1", "exchange")
    assert interaction is not None
    assert interaction.selector == "0x3df02124"


def test_aave_v3_protocol_details():
    reg = get_defi_registry()
    aave = reg.get("aave_v3")
    assert aave is not None
    assert aave.riskTier == 1
    pool_eth = aave.get_contract_address("1", "pool")
    assert pool_eth == "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
    supply_interaction = aave.get_interaction("1", "supply")
    assert supply_interaction is not None
    assert supply_interaction.selector == "0x617ba037"


def test_uniswap_v3_protocol_details():
    reg = get_defi_registry()
    uni = reg.get("uniswap_v3")
    assert uni is not None
    assert uni.riskTier == 2
    swap_router = uni.get_contract_address("1", "swapRouter")
    assert swap_router == "0xE592427A0AEce92De3Edee1F18E0157C05861564"
    exact_input = uni.get_interaction("1", "exactInputSingle")
    assert exact_input is not None
    assert exact_input.selector == "0x414bacae"


def test_resolve_target_and_interaction():
    reg = get_defi_registry()
    target = reg.resolve_target("compound_v3", "1", "cometUSDC")
    assert target == "0xc3d688B66703497DAA19211EEdff47f25384cdc3"

    nonexistent = reg.resolve_target("unknown_protocol", "1", "pool")
    assert nonexistent is None

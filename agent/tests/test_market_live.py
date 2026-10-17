"""Finding A: markets are either really executed on a chain or honestly reported as simulated — never faked."""

import os
import stat

import pytest
from eth_account import Account

from tecc_brain.models import ActionType, CardLabel, ExecutionIntent, usd_to_onchain
from tecc_brain.onchain.artifacts import Contract
from tecc_brain.onchain.deploy import deploy_local
from tecc_brain.onchain.executor import (
    ArbitrumCommoditiesExecutor,
    FiscoBcosExecutor,
    MarketRouter,
    PegGuardArbitrageExecutor,
    RecordLedger,
)
from tecc_brain.onchain.mandate import UserMandate, policy_hash
from tecc_brain.onchain.markets import MarketFile, build_router, load_market, market_path, save_market
from tecc_brain.onchain.rpc import Rpc
from tecc_brain.onchain.session import provision_session_key

# Anvil's well-known dev account #1: used here as a *funded external key*, i.e. the real-network signing path.
DEPLOYER_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"


def intent(venue="paxg_hold", usd=50.0, market="commodities", asset="USDC"):
    return ExecutionIntent(card_label=CardLabel.BETTER, venue_id=venue, action=ActionType.DEPOSIT, asset_in=asset,
                           amount_usd=usd, amount_onchain=usd_to_onchain(usd), market=market)


# --- honest simulation ---------------------------------------------------------------------------


@pytest.mark.parametrize("executor, market", [(FiscoBcosExecutor(), "chinese_market"),
                                              (ArbitrumCommoditiesExecutor(), "commodities")])
def test_without_a_node_the_market_is_simulated_never_faked(executor, market):
    out = executor.submit(intent(market=market), "demo")
    assert out.status == "simulated"
    assert out.tx_hash is None
    assert out.detail.startswith("SIMULATED:") and "deploy_market_chain.py" in out.detail
    assert not executor.is_live


def test_pegguard_plans_are_simulated_without_a_hash():
    out = PegGuardArbitrageExecutor().submit(
        intent(venue="curve_steth_eth", usd=200, market="arbitrage", asset="ETH").model_copy(
            update={"action": ActionType.BUY_DISCOUNT}), "demo")
    assert out.status in ("simulated", "failed")
    assert out.tx_hash is None
    if out.status == "simulated":
        assert "no orders were placed" in out.detail


def test_simulations_never_consume_the_daily_limit():
    router = MarketRouter(daily_limit_usd=500.0)
    router.submit(intent(usd=400.0), "alice", market="commodities")
    assert router.tether_tracker.get_spent("alice") == 0.0


def test_no_false_gas_claims_remain():
    out = FiscoBcosExecutor().submit(intent(market="chinese_market", venue="shibor_mmf"), "demo")
    assert "$0.00" not in out.detail and "settled" not in out.detail


# --- legacy fees (chains without EIP-1559, e.g. FISCO BCOS web3 RPC) ------------------------------


class FakeRpc(Rpc):
    def __init__(self, block):
        super().__init__("http://127.0.0.1:1")
        self.block = block

    def call(self, method, params=None):
        return {"eth_gasPrice": "0x3b9aca00", "eth_getBlockByNumber": self.block}[method]


def test_fee_fields_fall_back_to_legacy_gas_price():
    assert FakeRpc({"number": "0x1"}).fee_fields() == {"gasPrice": 10**9}
    eip1559 = FakeRpc({"number": "0x1", "baseFeePerGas": "0x1"}).fee_fields()
    assert eip1559["type"] == 2 and "maxFeePerGas" in eip1559


# --- live: a second chain (Arbitrum Sepolia's chain id) ---------------------------------------------


@pytest.fixture(scope="module")
def arbitrum(arbitrum_like_url):
    rpc = Rpc(arbitrum_like_url)
    assert rpc.chain_id() == 421614
    dep = deploy_local(rpc, eth_usd=2500.0, deployer_key=DEPLOYER_KEY, fund_eth_wei=10**17)  # signed, not unlocked
    session = Account.create()
    now = rpc.block_timestamp()
    mandate = UserMandate(account=dep.account, session_key=session.address, max_amount_usd=1000.0,
                          valid_after=now - 60, valid_until=now + 86_400, risk_tier=2,
                          policy=policy_hash(sorted(dep.venues)))
    provision_session_key(rpc, dep, mandate, fund_wei=10**17, owner_key=DEPLOYER_KEY)
    return rpc, dep, mandate, session


def test_signed_deployment_makes_the_key_the_root_owner(arbitrum):
    rpc, dep, *_ = arbitrum
    assert dep.chain_id == 421614
    assert dep.root_owner == Account.from_key(DEPLOYER_KEY).address
    policy = Contract.load("TetherGuardHook", dep.hook).call(rpc, "getAccountPolicy", dep.account)[0]
    assert policy[0] == 500 * 10**8


def test_commodities_executor_sends_a_real_vault_checked_transaction(arbitrum, tmp_path):
    rpc, dep, mandate, session = arbitrum
    executor = ArbitrumCommoditiesExecutor(rpc, dep, mandate, session_key=session.key,
                                           ledger=RecordLedger(tmp_path / "r.json"))
    assert executor.is_live
    out = executor.submit(intent(usd=50.0), "demo")
    assert out.status == "submitted", out.detail
    assert out.market == "commodities" and out.detail.startswith("Arbitrum (chain 421614)")
    receipt = rpc.call("eth_getTransactionReceipt", [out.tx_hash])
    assert receipt is not None and receipt["status"] == "0x1"  # the hash exists on that chain
    usdc = Contract.load("MockERC20", dep.usdc)
    assert usdc.call(rpc, "balanceOf", dep.venues["paxg_hold"])[0] == 50 * 10**6


def test_the_vault_on_that_chain_still_enforces_its_radius(arbitrum, tmp_path):
    rpc, dep, mandate, session = arbitrum
    executor = ArbitrumCommoditiesExecutor(rpc, dep, mandate, session_key=session.key,
                                           ledger=RecordLedger(tmp_path / "r.json"))
    out = executor.submit(intent(usd=900.0), "demo")
    assert out.status == "failed" and "TetherRadiusExceeded" in out.detail


def test_a_deployment_for_another_chain_is_refused_before_sending(arbitrum, tmp_path):
    rpc, dep, mandate, session = arbitrum
    wrong = dep.model_copy(update={"chain_id": 2026})
    out = FiscoBcosExecutor(rpc, wrong, mandate, session_key=session.key,
                            ledger=RecordLedger(tmp_path / "r.json")).submit(intent(market="chinese_market"), "demo")
    assert out.status == "failed" and "chain 421614" in out.detail and "2026" in out.detail


def test_market_files_make_the_router_live(arbitrum, tmp_path, monkeypatch):
    rpc, dep, mandate, session = arbitrum
    monkeypatch.setenv("TECC_STATE_DIR", str(tmp_path))
    path = save_market(MarketFile(network="arbitrum", rpc_url=rpc.url, deployment=dep, mandate=mandate,
                                  session_key="0x" + bytes(session.key).hex()))
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600  # holds a private key
    assert load_market("arbitrum").deployment == dep
    router = build_router(crypto_network="sepolia")
    assert router.commodities.is_live and not router.chinese_market.is_live
    out = router.submit(intent(usd=20.0), dep.account, market="commodities")
    assert out.status == "submitted", out.detail
    assert router.tether_tracker.get_spent(dep.account) == 20.0


def test_market_path_rejects_unknown_networks():
    with pytest.raises(ValueError):
        market_path("../../etc")

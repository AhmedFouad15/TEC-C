import pytest
from eth_account import Account

from tecc_brain.models import ActionType, CardLabel, ExecutionIntent, usd_to_onchain
from tecc_brain.onchain.artifacts import Contract
from tecc_brain.onchain.deploy import deploy_local
from tecc_brain.onchain.executor import ChainExecutor, RecordLedger
from tecc_brain.onchain.mandate import UserMandate, policy_hash
from tecc_brain.onchain.rpc import Rpc
from tecc_brain.onchain.session import provision_session_key


@pytest.fixture(scope="module")
def chain(anvil_url):
    rpc = Rpc(anvil_url)
    base = rpc.call("evm_snapshot", [])
    dep = deploy_local(rpc, eth_usd=2500.0)
    key = Account.create()
    now = rpc.block_timestamp()
    m = UserMandate(account=dep.account, session_key=key.address, max_amount_usd=1000.0, valid_after=now - 60,
                    valid_until=now + 86_400, risk_tier=2, policy=policy_hash(sorted(dep.venues)))
    provision_session_key(rpc, dep, m)
    yield rpc, dep, key, m
    rpc.call("evm_revert", [base])


@pytest.fixture
def fresh(chain, tmp_path):
    rpc, dep, key, m = chain
    snap = rpc.call("evm_snapshot", [])
    yield rpc, dep, key, m, RecordLedger(tmp_path / "records.json")
    rpc.call("evm_revert", [snap])


def intent(venue_id, usd, asset="USDC", action=ActionType.DEPOSIT):
    return ExecutionIntent(card_label=CardLabel.BETTER, venue_id=venue_id, action=action, asset_in=asset,
                           amount_usd=usd, amount_onchain=usd_to_onchain(usd))


def policy(rpc, dep):
    return Contract.load("TetherGuardHook", dep.hook).call(rpc, "getAccountPolicy", dep.account)[0]


def test_session_key_is_provisioned_with_the_mandate_root(chain):
    rpc, dep, key, m = chain
    validator = Contract.load("SessionKeyValidator", dep.validator)
    ok, root = validator.call(rpc, "verifyMandateCommitment", dep.account, key.address, m.digest(dep.chain_id, dep.validator))
    assert ok is True
    account = Contract.load("TecAccount", dep.account)
    assert account.call(rpc, "isModuleInstalled", 2, key.address, b"")[0] is True


def test_400_usdc_into_aave_runs_inside_the_tether(fresh):
    rpc, dep, key, m, ledger = fresh
    out = ChainExecutor(rpc, dep, key.key, m, ledger).submit(intent("aave_v3_usdc", 400), "demo")
    assert out.status == "submitted", out.detail
    assert out.tx_hash and "record #1" in out.detail
    assert policy(rpc, dep)[3] == 400 * 10**8  # dailySpent metered in USD by the hook
    usdc = Contract.load("MockERC20", dep.usdc)
    assert usdc.call(rpc, "balanceOf", dep.venues["aave_v3_usdc"])[0] == 400 * 10**6
    assert ledger.get(1).venue_id == "aave_v3_usdc"


def test_eth_stake_is_metered_through_the_eth_feed(fresh):
    rpc, dep, key, m, ledger = fresh
    out = ChainExecutor(rpc, dep, key.key, m, ledger).submit(
        intent("lido_stake", 250, asset="ETH", action=ActionType.STAKE), "demo")
    assert out.status == "submitted", out.detail
    assert abs(policy(rpc, dep)[3] - 250 * 10**8) <= 1


def test_the_vault_refuses_more_than_the_radius_before_anything_is_sent(fresh):
    rpc, dep, key, m, ledger = fresh
    nonce = rpc.call("eth_getTransactionCount", [key.address, "latest"])
    out = ChainExecutor(rpc, dep, key.key, m, ledger).submit(intent("aave_v3_usdc", 600), "demo")
    assert out.status == "failed" and "TetherRadiusExceeded" in out.detail
    assert rpc.call("eth_getTransactionCount", [key.address, "latest"]) == nonce


def test_tier_above_the_users_is_refused_on_chain(fresh):
    rpc, dep, key, m, ledger = fresh
    out = ChainExecutor(rpc, dep, key.key, m, ledger).submit(
        intent("uniswap_v3_usdc_eth", 100, asset="ETH"), "demo")
    assert out.status == "failed" and "AssetTierNotPermitted" in out.detail


def test_amount_above_the_mandate_never_reaches_the_chain(fresh):
    rpc, dep, key, m, ledger = fresh
    out = ChainExecutor(rpc, dep, key.key, m, ledger).submit(intent("aave_v3_usdc", 1500), "demo")
    assert out.status == "failed" and "mandate" in out.detail.lower()


def test_a_different_mandate_fails_the_validator_preflight(fresh):
    rpc, dep, key, m, ledger = fresh
    forged = m.model_copy(update={"max_amount_usd": 1_000_000.0})
    out = ChainExecutor(rpc, dep, key.key, forged, ledger).submit(intent("aave_v3_usdc", 100), "demo")
    assert out.status == "failed" and "validator" in out.detail.lower()


def test_an_unprovisioned_key_fails_the_preflight(fresh):
    rpc, dep, key, m, ledger = fresh
    stranger = Account.create()
    out = ChainExecutor(rpc, dep, stranger.key, m, ledger).submit(intent("aave_v3_usdc", 100), "demo")
    assert out.status == "failed"

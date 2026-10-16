import pytest

from tecc_brain.onchain.artifacts import Contract
from tecc_brain.onchain.deploy import LocalDeployment, deploy_local
from tecc_brain.onchain.rpc import Rpc, RpcError
from tecc_brain.reference import load_reference

REF = load_reference()


@pytest.fixture(scope="module")
def chain(anvil_url):
    rpc = Rpc(anvil_url)
    snapshot = rpc.call("evm_snapshot", [])
    dep = deploy_local(rpc, eth_usd=2500.0)
    yield rpc, dep
    rpc.call("evm_revert", [snapshot])


def test_policy_is_in_eight_decimal_usd(chain):
    rpc, dep = chain
    hook = Contract.load("TetherGuardHook", dep.hook)
    policy = hook.call(rpc, "getAccountPolicy", dep.account)[0]
    radius, baseline, ceiling = policy[0], policy[1], policy[2]
    assert radius == baseline == 500 * 10**8
    assert ceiling == 2000 * 10**8
    assert policy[5] == 2 and policy[6] is True  # Balanced tier, elasticity on


def test_every_venue_is_whitelisted_with_its_tier(chain):
    rpc, dep = chain
    hook = Contract.load("TetherGuardHook", dep.hook)
    for venue_id, address in dep.venues.items():
        assert hook.call(rpc, "whitelistedTargets", dep.account, address)[0] is True
        assert hook.call(rpc, "targetRiskTiers", dep.account, address)[0] == REF.venues[venue_id].tier
    assert set(dep.venues) == set(REF.venues)


def test_account_is_funded(chain):
    rpc, dep = chain
    usdc = Contract.load("MockERC20", dep.usdc)
    assert usdc.call(rpc, "balanceOf", dep.account)[0] == 100_000 * 10**6
    assert int(rpc.call("eth_getBalance", [dep.account, "latest"]), 16) == 10 * 10**18


def test_feeds_price_eth_and_usdc(chain):
    rpc, dep = chain
    hook = Contract.load("TetherGuardHook", dep.hook)
    assert hook.call(rpc, "getLatestPrice", dep.account, dep.usdc)[0] == 10**8
    native = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
    assert hook.call(rpc, "getLatestPrice", dep.account, native)[0] == 2500 * 10**8


def test_deployment_file_round_trips(chain, tmp_path):
    _, dep = chain
    path = dep.save(tmp_path / "contracts.local.json")
    assert LocalDeployment.load(path) == dep


def test_rpc_errors_carry_the_revert(chain):
    rpc, dep = chain
    hook = Contract.load("TetherGuardHook", dep.hook)
    with pytest.raises(RpcError) as err:
        hook.call(rpc, "ratifyTransaction", dep.account, 999, sender=dep.root_owner)
    assert hook.decode_error(err.value.data) == "InvalidRecordId()"

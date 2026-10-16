"""Deploy Member 1's vault suite plus mocks to a local Anvil chain, the way the Brain needs it for the demo.

Differences from `script/DeployTecC.s.sol` (left untouched): the radius is set in 8-decimal USD (what the hook meters
once price feeds exist) with elasticity on, ETH/USD and USDC/USD mock feeds are configured, and every venue in
venues.json gets a mock protocol whitelisted with its tier. Anvil account 0 stands in for the FaceID root owner.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from tecc_brain.models import usd_to_onchain
from tecc_brain.onchain.artifacts import NATIVE_ETH, Contract
from tecc_brain.onchain.rpc import Rpc
from tecc_brain.reference import Reference, load_reference

STATE_FILE = Path(__file__).resolve().parents[2] / ".state" / "contracts.local.json"
NO_BUNDLER_ENTRYPOINT = "0x000000000000000000000000000000000000dEaD"  # no 4337 bundler: execution uses the executor path
USDC_DECIMALS = 6
FUNDED_USDC = 100_000
FUNDED_ETH_WEI = 10 * 10**18


class LocalDeployment(BaseModel):
    chain_id: int
    root_owner: str
    hook: str
    validator: str
    account: str
    usdc: str
    eth_feed: str
    usdc_feed: str
    venues: dict[str, str]
    eth_usd: float
    deployed_block: int

    def save(self, path: Path = STATE_FILE) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: Path = STATE_FILE) -> "LocalDeployment":
        return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def deploy_local(
    rpc: Rpc,
    *,
    eth_usd: float,
    radius_usd: float = 500.0,
    ceiling_usd: float = 2000.0,
    tier: int = 2,
    ref: Reference | None = None,
) -> LocalDeployment:
    ref = ref or load_reference()
    owner = rpc.call("eth_accounts")[0]

    hook = Contract.load("TetherGuardHook").deploy(rpc, owner)
    validator = Contract.load("SessionKeyValidator").deploy(rpc, owner)
    account = Contract.load("TecAccount").deploy(rpc, owner, NO_BUNDLER_ENTRYPOINT)
    account.transact(rpc, "initialize", owner, hook.address, validator.address, sender=owner)

    feed = Contract.load("MockChainlinkFeed")
    eth_feed = feed.deploy(rpc, owner, 8, usd_to_onchain(eth_usd), "ETH / USD")
    usdc_feed = feed.deploy(rpc, owner, 8, usd_to_onchain(1.0), "USDC / USD")
    usdc = Contract.load("MockERC20").deploy(rpc, owner, "USD Coin", "USDC", USDC_DECIMALS)
    usdc.transact(rpc, "mint", account.address, FUNDED_USDC * 10**USDC_DECIMALS, sender=owner)

    hook.transact(rpc, "setGlobalPriceFeed", NATIVE_ETH, eth_feed.address, sender=owner)
    hook.transact(rpc, "setGlobalPriceFeed", usdc.address, usdc_feed.address, sender=owner)
    hook.transact(
        rpc, "initializeAccountPolicy", account.address, owner, usd_to_onchain(radius_usd), tier, True,
        usd_to_onchain(ceiling_usd), sender=owner,
    )
    # USDC moves are ERC-20 transfers whose call target is the token itself, so the token is whitelisted too
    # (tier 1, a core stablecoin). See SUMMARY: the hook does not check the transfer's recipient.
    hook.transact(rpc, "setTargetWhitelist", account.address, usdc.address, True, 1, sender=owner)

    protocol = Contract.load("MockDeFiProtocol")
    venues: dict[str, str] = {}
    for venue in ref.venues.values():
        mock = protocol.deploy(rpc, owner)
        hook.transact(rpc, "setTargetWhitelist", account.address, mock.address, True, int(venue.tier), sender=owner)
        venues[venue.id] = mock.address  # type: ignore[assignment]

    rpc.send_unlocked({"from": owner, "to": account.address, "value": hex(FUNDED_ETH_WEI)})
    return LocalDeployment(
        chain_id=rpc.chain_id(), root_owner=owner, hook=hook.address, validator=validator.address,  # type: ignore[arg-type]
        account=account.address, usdc=usdc.address, eth_feed=eth_feed.address, usdc_feed=usdc_feed.address,  # type: ignore[arg-type]
        venues=venues, eth_usd=eth_usd, deployed_block=int(rpc.call("eth_blockNumber"), 16),
    )

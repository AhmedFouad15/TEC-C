"""Network selection: Anvil (local demo) vs Ethereum Sepolia (submission chain), on the SAME stdlib RPC client
and the SAME eth_account signing path already used by `onchain/executor.py` and `onchain/session.py`.

Deliberately does not introduce web3.py anywhere: `onchain/rpc.py`'s `Rpc` already speaks JSON-RPC directly
over `urllib.request`, and `ChainExecutor.submit()` already signs with `eth_account.Account.sign_transaction`
and sends with `rpc.send_raw(...)` — that path works against any JSON-RPC endpoint, Anvil or Sepolia alike.
The only Anvil-specific code is `deploy_local()` / `provision_session_key()`'s use of `send_unlocked`
(`eth_accounts` + `eth_sendTransaction` from a node-managed key), which only runs for local deploys and is
never called on Sepolia: Sepolia contracts are deployed once via Member 1's `forge script`, and this module
just *loads* the resulting addresses from `shared/contracts.sepolia.json` into the same `LocalDeployment`
shape `ChainExecutor` already expects — no new dependency, no new signing path.

Env vars:
    TECC_NETWORK           "anvil" (default) or "sepolia"
    TECC_ANVIL_RPC_URL      default http://127.0.0.1:8545
    SEPOLIA_RPC_URL         required when TECC_NETWORK=sepolia (e.g. an Alchemy/Infura HTTPS endpoint)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from tecc_brain.onchain.deploy import LocalDeployment
from tecc_brain.onchain.rpc import Rpc
from tecc_brain.reference import Reference, load_reference

NetworkName = Literal["anvil", "sepolia"]

REPO_ROOT = Path(__file__).resolve().parents[3]
SEPOLIA_CONTRACTS_FILE = REPO_ROOT / "shared" / "contracts.sepolia.json"
DEAD_ADDRESS = "0x0000000000000000000000000000000000dEaD"

DEFAULT_ANVIL_RPC = "http://127.0.0.1:8545"


class NetworkConfigError(RuntimeError):
    """Raised when the selected network is missing required config (e.g. an undeployed Sepolia address)."""


def current_network() -> NetworkName:
    value = os.environ.get("TECC_NETWORK", "anvil").strip().lower()
    if value not in ("anvil", "sepolia"):
        raise NetworkConfigError(f"TECC_NETWORK must be 'anvil' or 'sepolia', got {value!r}")
    return value  # type: ignore[return-value]


def rpc_url_for(network: NetworkName | None = None) -> str:
    network = network or current_network()
    if network == "anvil":
        return os.environ.get("TECC_ANVIL_RPC_URL", DEFAULT_ANVIL_RPC)
    url = os.environ.get("SEPOLIA_RPC_URL")
    if not url:
        raise NetworkConfigError(
            "SEPOLIA_RPC_URL is not set. Point it at an HTTPS JSON-RPC endpoint (Alchemy, Infura, your own node)."
        )
    if not url.startswith("https://"):
        raise NetworkConfigError("SEPOLIA_RPC_URL must be https:// (the Rpc client refuses non-local http)")
    return url


def make_rpc(network: NetworkName | None = None) -> Rpc:
    return Rpc(rpc_url_for(network))


def _load_sepolia_json(path: Path = SEPOLIA_CONTRACTS_FILE) -> dict:
    if not path.exists():
        raise NetworkConfigError(f"{path} is missing — copy shared/contracts.sepolia.json into place first")
    return json.loads(path.read_text(encoding="utf-8"))


def _require_deployed(name: str, address: str) -> str:
    if not address or address.lower() == DEAD_ADDRESS.lower():
        raise NetworkConfigError(
            f"{name} has no Sepolia address yet in shared/contracts.sepolia.json — "
            "ask the smart-contract engineer to fill it in after `forge script Deploy --broadcast`."
        )
    return address


def load_sepolia_deployment(
    rpc: Rpc, *, ref: Reference | None = None, eth_usd: float | None = None, path: Path = SEPOLIA_CONTRACTS_FILE
) -> LocalDeployment:
    """Build the same `LocalDeployment` shape `ChainExecutor` already consumes, from the Sepolia config file
    instead of a local `deploy_local()` run. No contracts are deployed here — only addresses are read.

    `eth_usd` lets a caller pass a freshly-read oracle price (e.g. from `TetherGuardHook.getLatestPrice`);
    if omitted, a conservative placeholder is used only for off-chain sizing display, never for on-chain checks
    (the hook re-prices everything on-chain regardless of what the Brain believes the price is).
    """
    ref = ref or load_reference()
    raw = _load_sepolia_json(path)
    meta, addresses = raw["_meta"], raw["deployedAddresses"]
    venue_addresses: dict[str, str] = {
        k: v for k, v in raw.get("venues", {}).items() if k != "note" and v and v.lower() != DEAD_ADDRESS.lower()
    }
    missing_venues = [v.id for v in ref.venues.values() if v.id not in venue_addresses]
    if missing_venues:
        raise NetworkConfigError(
            f"shared/contracts.sepolia.json has no Sepolia address for venue(s) {missing_venues}; "
            "the Econometric & Liquidity agent can still SCORE them from market data, but the Web3 Executor "
            "cannot route funds to them until an address is added under `venues`."
        )
    return LocalDeployment(
        chain_id=int(meta["chainId"]),
        root_owner=addresses.get("TecAccount", DEAD_ADDRESS),  # Sepolia: the FaceID owner is the account's root owner, not a dev key
        hook=_require_deployed("TetherGuardHook", addresses.get("TetherGuardHook", "")),
        validator=_require_deployed("SessionKeyValidator", addresses.get("SessionKeyValidator", "")),
        account=_require_deployed("TecAccount", addresses.get("TecAccount", "")),
        usdc=_require_deployed("USDC", addresses.get("USDC", "")),
        eth_feed=_require_deployed("ETHUSDFeed", addresses.get("ETHUSDFeed", "")),
        usdc_feed=addresses.get("USDCUSDFeed", DEAD_ADDRESS),
        venues=venue_addresses,
        eth_usd=eth_usd if eth_usd is not None else 3000.0,  # display-only fallback; never used for on-chain math
        deployed_block=int(rpc.call("eth_blockNumber"), 16),
    )


def make_deployment(
    rpc: Rpc, *, network: NetworkName | None = None, ref: Reference | None = None, eth_usd: float | None = None
) -> LocalDeployment:
    """Dispatch to the local Anvil state file or the Sepolia config file, keyed by TECC_NETWORK."""
    network = network or current_network()
    if network == "anvil":
        return LocalDeployment.load()
    return load_sepolia_deployment(rpc, ref=ref, eth_usd=eth_usd)


__all__ = [
    "NetworkConfigError", "NetworkName", "current_network", "load_sepolia_deployment", "make_deployment",
    "make_rpc", "rpc_url_for",
]

"""Which markets are live: a market becomes live after `scripts/deploy_market_chain.py` has deployed the vault on its
chain and provisioned a session key. Everything else stays `simulated` — never a fabricated transaction.

State per network, under TECC_STATE_DIR (default agent/.state, git-ignored):
    markets/<network>.json   deployment addresses + node URL + the owner's mandate + the session key (mode 0600)
The session key is the Brain's own, limited key (bound to one mandate, revocable by the owner); the owner's
deployer key is never stored.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel

from tecc_brain.onchain.deploy import LocalDeployment
from tecc_brain.onchain.executor import (
    ArbitrumCommoditiesExecutor,
    ChainExecutor,
    FiscoBcosExecutor,
    MarketRouter,
    RecordLedger,
)
from tecc_brain.onchain.mandate import UserMandate
from tecc_brain.onchain.rpc import Rpc

DEFAULT_STATE_DIR = Path(__file__).resolve().parents[2] / ".state"
NETWORKS = ("anvil", "sepolia", "arbitrum", "fisco_bcos")


class MarketFile(BaseModel):
    network: str
    rpc_url: str
    deployment: LocalDeployment
    mandate: UserMandate
    session_key: str  # 0x-hex private key of the Brain's session key (not the owner's key)


def state_dir() -> Path:
    return Path(os.environ.get("TECC_STATE_DIR", DEFAULT_STATE_DIR))


def market_path(network: str) -> Path:
    if network not in NETWORKS:
        raise ValueError(f"network must be one of {NETWORKS}")
    return state_dir() / "markets" / f"{network}.json"


def save_market(market: MarketFile) -> Path:
    path = market_path(market.network)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # holds a private key: owner-only
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(market.model_dump_json(indent=2))
    return path


def load_market(network: str) -> MarketFile | None:
    path = market_path(network)
    return MarketFile.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def _ledger(network: str) -> RecordLedger:
    return RecordLedger(state_dir() / "markets" / f"{network}.records.json")


def live_chain_executor(network: str) -> ChainExecutor | None:
    m = load_market(network)
    if m is None:
        return None
    return ChainExecutor(Rpc(m.rpc_url), m.deployment, m.session_key, m.mandate, _ledger(network))


def build_router(daily_limit_usd: float = 500.0, crypto_network: str | None = None) -> MarketRouter:
    """Live executors for every market that has been deployed; honest simulations for the rest."""
    crypto_network = crypto_network or os.environ.get("TECC_NETWORK", "anvil")
    executors = {}
    for market, cls, network in (
        ("commodities", ArbitrumCommoditiesExecutor, "arbitrum"),
        ("chinese_market", FiscoBcosExecutor, "fisco_bcos"),
    ):
        m = load_market(network)
        executors[market] = (
            cls(Rpc(m.rpc_url), m.deployment, m.mandate, session_key=m.session_key, ledger=_ledger(network))
            if m else cls()
        )
    return MarketRouter(
        crypto=live_chain_executor(crypto_network),
        commodities=executors["commodities"],
        chinese_market=executors["chinese_market"],
        daily_limit_usd=daily_limit_usd,
    )


__all__ = ["MarketFile", "NETWORKS", "build_router", "live_chain_executor", "load_market", "market_path", "save_market"]

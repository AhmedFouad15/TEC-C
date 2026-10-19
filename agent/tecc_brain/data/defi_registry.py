"""DeFi Protocol Registry loader and query engine.

Reads protocol contracts, function selectors, ABIs, and risk tiers from `shared/defi_protocols.json`
so executors know exactly what contract and calldata format to use across chains.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

DEFI_PROTOCOLS_FILE = Path(__file__).resolve().parents[3] / "shared" / "defi_protocols.json"


class InteractionParam(BaseModel):
    name: str
    type: str
    components: list[dict[str, Any]] | None = None


class ProtocolInteraction(BaseModel):
    targetContract: str
    function: str
    selector: str
    isPayable: bool = False
    inputs: list[InteractionParam] = Field(default_factory=list)
    defaultReferral: str | None = None


class ChainProtocolDeployment(BaseModel):
    network: str
    contracts: dict[str, str] = Field(default_factory=dict)
    interactions: dict[str, ProtocolInteraction] = Field(default_factory=dict)


class DefiProtocol(BaseModel):
    id: str
    name: str
    category: str
    riskTier: int
    chains: dict[str, ChainProtocolDeployment] = Field(default_factory=dict)

    def get_chain(self, chain_id: int | str) -> ChainProtocolDeployment | None:
        return self.chains.get(str(chain_id))

    def get_contract_address(self, chain_id: int | str, contract_key: str) -> str | None:
        chain = self.get_chain(chain_id)
        if not chain:
            return None
        return chain.contracts.get(contract_key)

    def get_interaction(self, chain_id: int | str, interaction_name: str) -> ProtocolInteraction | None:
        chain = self.get_chain(chain_id)
        if not chain:
            return None
        return chain.interactions.get(interaction_name)


class DefiRegistry:
    def __init__(self, file_path: Path = DEFI_PROTOCOLS_FILE) -> None:
        self.file_path = file_path
        self._protocols: dict[str, DefiProtocol] = {}
        self.reload()

    def reload(self) -> None:
        if not self.file_path.exists():
            return
        data = json.loads(self.file_path.read_text(encoding="utf-8"))
        raw_protocols = data.get("protocols", {})
        self._protocols = {
            pid: DefiProtocol.model_validate(pdata)
            for pid, pdata in raw_protocols.items()
        }

    def get(self, protocol_id: str) -> DefiProtocol | None:
        return self._protocols.get(protocol_id.lower().strip())

    def list_all(self) -> list[DefiProtocol]:
        return list(self._protocols.values())

    def resolve_target(self, protocol_id: str, chain_id: int | str, contract_name: str) -> str | None:
        proto = self.get(protocol_id)
        if not proto:
            return None
        return proto.get_contract_address(chain_id, contract_name)

    def resolve_interaction(
        self, protocol_id: str, chain_id: int | str, interaction_name: str
    ) -> ProtocolInteraction | None:
        proto = self.get(protocol_id)
        if not proto:
            return None
        return proto.get_interaction(chain_id, interaction_name)


_GLOBAL_REGISTRY: DefiRegistry | None = None


def get_defi_registry() -> DefiRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = DefiRegistry()
    return _GLOBAL_REGISTRY


__all__ = [
    "ChainProtocolDeployment",
    "DefiProtocol",
    "DefiRegistry",
    "InteractionParam",
    "ProtocolInteraction",
    "get_defi_registry",
]

"""EIP-712 UserMandate: what the owner authorises the Brain's session key to do. Its digest is the session key's
on-chain `mandateRoot` (SessionKeyValidator), and travels in every 117-byte session signature.

    UserMandate(address account, address sessionKey, uint256 maxAmountUsd, uint48 validAfter, uint48 validUntil,
                uint8 riskTier, bytes32 policyHash)
    domain = {name: "Tec-C UserMandate", version: "1", chainId, verifyingContract: SessionKeyValidator}

maxAmountUsd is 8-decimal USD (the hook's unit). policyHash commits to the venues the Brain may use.
"""

from __future__ import annotations

import json
from typing import Any

from eth_abi import encode
from eth_utils import keccak, to_checksum_address
from pydantic import BaseModel, Field

from tecc_brain.models import usd_to_onchain

DOMAIN_NAME = "Tec-C UserMandate"
DOMAIN_VERSION = "1"
DOMAIN_TYPE = "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
MANDATE_TYPE = (
    "UserMandate(address account,address sessionKey,uint256 maxAmountUsd,uint48 validAfter,uint48 validUntil,"
    "uint8 riskTier,bytes32 policyHash)"
)
TYPES: dict[str, list[dict[str, str]]] = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "UserMandate": [
        {"name": "account", "type": "address"},
        {"name": "sessionKey", "type": "address"},
        {"name": "maxAmountUsd", "type": "uint256"},
        {"name": "validAfter", "type": "uint48"},
        {"name": "validUntil", "type": "uint48"},
        {"name": "riskTier", "type": "uint8"},
        {"name": "policyHash", "type": "bytes32"},
    ],
}


def policy_hash(venue_ids: list[str]) -> str:
    """keccak256 of the sorted allowed venue ids (canonical JSON), as 0x-hex."""
    return "0x" + keccak(text=json.dumps(sorted(venue_ids), separators=(",", ":"))).hex()


class UserMandate(BaseModel):
    account: str
    session_key: str
    max_amount_usd: float = Field(gt=0)
    valid_after: int = Field(ge=0, lt=2**48)
    valid_until: int = Field(ge=0, lt=2**48)
    risk_tier: int = Field(ge=1, le=3)
    policy: str = Field(pattern=r"^0x[0-9a-fA-F]{64}$")

    def message(self) -> dict[str, Any]:
        return {
            "account": to_checksum_address(self.account),
            "sessionKey": to_checksum_address(self.session_key),
            "maxAmountUsd": usd_to_onchain(self.max_amount_usd),
            "validAfter": self.valid_after,
            "validUntil": self.valid_until,
            "riskTier": self.risk_tier,
            "policyHash": bytes.fromhex(self.policy[2:]),
        }

    def typed_data(self, chain_id: int, validator: str) -> dict[str, Any]:
        return {
            "types": TYPES,
            "primaryType": "UserMandate",
            "domain": {"name": DOMAIN_NAME, "version": DOMAIN_VERSION, "chainId": chain_id,
                       "verifyingContract": to_checksum_address(validator)},
            "message": self.message(),
        }

    def digest(self, chain_id: int, validator: str) -> bytes:
        domain = keccak(encode(
            ["bytes32", "bytes32", "bytes32", "uint256", "address"],
            [keccak(text=DOMAIN_TYPE), keccak(text=DOMAIN_NAME), keccak(text=DOMAIN_VERSION), chain_id,
             to_checksum_address(validator)],
        ))
        m = self.message()
        struct = keccak(encode(
            ["bytes32", "address", "address", "uint256", "uint48", "uint48", "uint8", "bytes32"],
            [keccak(text=MANDATE_TYPE), m["account"], m["sessionKey"], m["maxAmountUsd"], m["validAfter"],
             m["validUntil"], m["riskTier"], m["policyHash"]],
        ))
        return keccak(b"\x19\x01" + domain + struct)

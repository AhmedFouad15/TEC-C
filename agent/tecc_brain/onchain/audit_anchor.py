"""Privacy-Preserving On-Chain Audit Anchors for WeBank's FISCO BCOS consortium chain (Section 2).

When Tec-C detects a de-peg, logs a user note, or executes an arbitrage trade, it commits
a cryptographic SHA-256 digest to FISCO BCOS:
    RecordHash = SHA256(account || symbol || action || P_cons || timestamp || salt)

Emits an immutable AuditRecordAnchored event on the consortium chain. Proprietary quantitative
curves and client trade secrets remain strictly private off-chain, while WeBank's FISCO BCOS
provides a tamper-proof regulatory compliance trail for enterprise auditing.
"""

from __future__ import annotations

from enum import IntEnum
import hashlib
import time
from typing import Any

from eth_account import Account

from tecc_brain.onchain.artifacts import Contract
from tecc_brain.onchain.rpc import GAS_HEADROOM, GAS_MARGIN, Rpc


class AuditRecordType(IntEnum):
    DEPEG_DETECTED = 0
    MORNING_REVIEW_NOTE = 1
    ARBITRAGE_EXECUTED = 2


def compute_audit_record_hash(
    account: str,
    symbol: str,
    action: str,
    p_cons: float,
    timestamp: int | float | None = None,
    salt: str = "",
) -> str:
    """Compute deterministic SHA-256 digest of private event parameters.

    Returns 0x-prefixed 32-byte hex string.
    """
    ts = int(timestamp if timestamp is not None else time.time())
    canonical_repr = f"{account.lower()}|{symbol.upper()}|{action.upper()}|{p_cons:.6f}|{ts}|{salt}"
    digest = hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()
    return "0x" + digest


class PrivacyAuditAnchorClient:
    """Interacts with PrivacyAuditAnchor smart contract on FISCO BCOS."""

    def __init__(self, rpc: Rpc, anchor_address: str, signer_key: str | bytes | None = None) -> None:
        self.rpc = rpc
        self.anchor_address = anchor_address
        self.contract = Contract.load("PrivacyAuditAnchor", anchor_address)
        self.account = Account.from_key(signer_key) if signer_key else None

    def anchor_record(
        self,
        record_hash: str | bytes,
        record_type: AuditRecordType | int = AuditRecordType.DEPEG_DETECTED,
    ) -> str:
        """Commit an audit hash to FISCO BCOS, emitting an on-chain event.

        Returns transaction hash.
        """
        if not self.account:
            raise ValueError("Signer private key required to anchor audit records on-chain.")

        hash_bytes = bytes.fromhex(record_hash[2:] if str(record_hash).startswith("0x") else record_hash)
        if len(hash_bytes) != 32:
            raise ValueError(f"record_hash must be exactly 32 bytes, got {len(hash_bytes)}")

        calldata = self.contract.encode("anchorRecord", hash_bytes, int(record_type))
        tx = {
            "from": self.account.address,
            "to": self.anchor_address,
            "data": "0x" + calldata.hex(),
        }

        gas = int(self.rpc.call("eth_estimateGas", [tx]), 16)
        chain_id = self.rpc.chain_id()

        signed = Account.sign_transaction({
            **self.rpc.fee_fields(),
            "chainId": chain_id,
            "to": self.anchor_address,
            "data": "0x" + calldata.hex(),
            "value": 0,
            "nonce": int(self.rpc.call("eth_getTransactionCount", [self.account.address, "pending"]), 16),
            "gas": int(gas * GAS_MARGIN) + GAS_HEADROOM,
        }, self.account.key)

        receipt = self.rpc.send_raw("0x" + bytes(signed.raw_transaction).hex())
        return receipt["transactionHash"]

    def verify_record(self, record_hash: str | bytes) -> tuple[bool, int]:
        """Query consortium chain to verify if a record hash was anchored.

        Returns (is_anchored, timestamp).
        """
        hash_bytes = bytes.fromhex(record_hash[2:] if str(record_hash).startswith("0x") else record_hash)
        res = self.contract.call(self.rpc, "verifyRecord", hash_bytes)
        is_anchored, ts = bool(res[0]), int(res[1])
        return (is_anchored, ts)

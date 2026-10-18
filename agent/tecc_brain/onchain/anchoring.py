"""Anchors computed audit hashes on FISCO BCOS through `PrivacyAuditAnchor.anchorRecord` (docs/06 §1).

Live only when all three are known, otherwise every call reports `not_configured` (never a fake anchor):
    TECC_AUDIT_ANCHOR_ADDRESS   the deployed PrivacyAuditAnchor contract
    TECC_AUDIT_ANCHOR_RPC_URL   FISCO BCOS web3 RPC   (default: the fisco_bcos market file's node, if deployed)
    TECC_AUDIT_ANCHOR_KEY       signer private key    (default: the fisco_bcos market file's session key)

What is anchored (the contract's three record types): PegGuard de-pegs detected from market data
(DEPEG_DETECTED), arbitrage trades actually submitted (ARBITRAGE_EXECUTED) and Morning Review notes
(MORNING_REVIEW_NOTE). Only the 32-byte digest goes on chain; the pre-image stays off-chain.
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel

from tecc_brain.onchain.audit_anchor import AuditRecordType, PrivacyAuditAnchorClient
from tecc_brain.onchain.rpc import Rpc

AnchorStatus = Literal["anchored", "not_configured", "failed"]


class AnchorResult(BaseModel):
    status: AnchorStatus
    record_hash: str
    tx_hash: str | None = None
    detail: str = ""


class AuditAnchorService:
    def __init__(self, client: PrivacyAuditAnchorClient | None = None, reason: str = "") -> None:
        self.client = client
        self.reason = reason or "no PrivacyAuditAnchor configured (set TECC_AUDIT_ANCHOR_ADDRESS)"

    @property
    def live(self) -> bool:
        return self.client is not None

    @classmethod
    def from_env(cls) -> "AuditAnchorService":
        address = os.environ.get("TECC_AUDIT_ANCHOR_ADDRESS")
        rpc_url = os.environ.get("TECC_AUDIT_ANCHOR_RPC_URL")
        key = os.environ.get("TECC_AUDIT_ANCHOR_KEY")
        if address and not (rpc_url and key):
            from tecc_brain.onchain.markets import load_market

            try:
                fisco = load_market("fisco_bcos")
            except (OSError, ValueError):
                fisco = None
            if fisco is not None:
                rpc_url, key = rpc_url or fisco.rpc_url, key or fisco.session_key
        if not (address and rpc_url and key):
            return cls(None)
        try:
            return cls(PrivacyAuditAnchorClient(Rpc(rpc_url), address, key))
        except (OSError, ValueError) as exc:  # e.g. contract artifacts not built
            return cls(None, reason=f"PrivacyAuditAnchor unavailable: {exc}")

    def anchor(self, record_hash: str | None, record_type: AuditRecordType) -> AnchorResult | None:
        if not record_hash:
            return None
        if self.client is None:
            return AnchorResult(status="not_configured", record_hash=record_hash, detail=self.reason)
        try:
            tx = self.client.anchor_record(record_hash, record_type)
        except Exception as exc:  # noqa: BLE001 — a node error must never break the trade/review it documents
            return AnchorResult(status="failed", record_hash=record_hash, detail=f"{exc.__class__.__name__}: {exc}")
        return AnchorResult(status="anchored", record_hash=record_hash, tx_hash=tx)


__all__ = ["AnchorResult", "AnchorStatus", "AuditAnchorService"]

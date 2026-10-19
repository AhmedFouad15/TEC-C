"""Cross-Chain Bridge Relayer for Tether Radius Synchronization.

Relays cryptographic spend proofs across Ethereum Mainnet, Arbitrum One, and FISCO BCOS.
Enforces institutional multi-chain invariant:
If $500 is spent on Ethereum and the daily tether radius is $500, the relayer broadcasts
cryptographically signed spend proofs to Arbitrum and FISCO BCOS, locking spending
across all consortium chains.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import keccak, to_checksum_address
from pydantic import BaseModel, Field

from tecc_brain.models import usd_to_onchain
from tecc_brain.onchain.artifacts import Contract
from tecc_brain.onchain.rpc import GAS_HEADROOM, GAS_MARGIN, Rpc

logger = logging.getLogger(__name__)


class CrossChainSpendProof(BaseModel):
    account: str
    source_chain_id: int
    amount_usd_raw: int
    epoch: int
    nonce: int
    deadline: int

    @classmethod
    def create(
        cls,
        account: str,
        source_chain_id: int,
        amount_usd: float,
        epoch: int | None = None,
        nonce: int | None = None,
        ttl_seconds: int = 3600,
    ) -> CrossChainSpendProof:
        now = int(time.time())
        ep = epoch if epoch is not None else (now // 86400)
        nc = nonce if nonce is not None else int(time.time() * 1000) % (2**64)
        return cls(
            account=to_checksum_address(account),
            source_chain_id=source_chain_id,
            amount_usd_raw=usd_to_onchain(amount_usd),
            epoch=ep,
            nonce=nc,
            deadline=now + ttl_seconds,
        )

    @property
    def amount_usd(self) -> float:
        return self.amount_usd_raw / 1e8

    def to_tuple(self) -> tuple[str, int, int, int, int, int]:
        return (
            self.account,
            self.source_chain_id,
            self.amount_usd_raw,
            self.epoch,
            self.nonce,
            self.deadline,
        )


def compute_proof_message_hash(
    proof: CrossChainSpendProof, dest_chain_id: int, dest_hook_address: str
) -> bytes:
    """Computes the inner message hash matching TetherGuardHook.sol:1304-1315."""
    encoded = encode(
        ["address", "uint256", "uint256", "uint256", "uint256", "uint256", "uint256", "address"],
        [
            to_checksum_address(proof.account),
            proof.source_chain_id,
            proof.amount_usd_raw,
            proof.epoch,
            proof.nonce,
            proof.deadline,
            dest_chain_id,
            to_checksum_address(dest_hook_address),
        ],
    )
    return keccak(encoded)


def sign_spend_proof(
    proof: CrossChainSpendProof,
    dest_chain_id: int,
    dest_hook_address: str,
    signer_key: str | bytes,
) -> bytes:
    """Signs the spend proof with EIP-191 personal sign prefix matching Solidity ecrecover."""
    message_hash = compute_proof_message_hash(proof, dest_chain_id, dest_hook_address)
    signable = encode_defunct(primitive=message_hash)
    signed = Account.sign_message(signable, signer_key)
    return bytes(signed.signature)


class PeerChainConfig(BaseModel):
    chain_id: int
    network_name: str
    rpc_url: str
    hook_address: str


class CrossChainBridgeRelayer:
    """Monitors spending and relays signed proofs to destination chains."""

    def __init__(
        self,
        relayer_key: str | bytes | None = None,
        peer_chains: dict[int, PeerChainConfig] | None = None,
    ) -> None:
        self.relayer_key = relayer_key
        self.peer_chains: dict[int, PeerChainConfig] = peer_chains or {}
        self._nonces: dict[str, int] = {}

    def register_peer(self, config: PeerChainConfig) -> None:
        self.peer_chains[config.chain_id] = config

    def _next_nonce(self, account: str) -> int:
        acc = account.lower()
        if acc not in self._nonces:
            self._nonces[acc] = int(time.time())
        self._nonces[acc] += 1
        return self._nonces[acc]

    def relay_spend_to_chain(
        self,
        dest_chain_id: int,
        account: str,
        source_chain_id: int,
        amount_usd: float,
        signer_key: str | bytes | None = None,
        epoch: int | None = None,
    ) -> dict[str, Any]:
        """Relays a spend proof to a specific destination chain."""
        key = signer_key or self.relayer_key
        if not key:
            raise ValueError("No signer/relayer key provided for signing cross-chain spend proof")

        peer = self.peer_chains.get(dest_chain_id)
        if not peer:
            raise ValueError(f"Destination chain {dest_chain_id} is not registered in the relayer")

        rpc = Rpc(peer.rpc_url)
        hook = Contract.load("TetherGuardHook", peer.hook_address)

        nonce = self._next_nonce(account)
        proof = CrossChainSpendProof.create(
            account=account,
            source_chain_id=source_chain_id,
            amount_usd=amount_usd,
            epoch=epoch,
            nonce=nonce,
        )

        signature = sign_spend_proof(proof, dest_chain_id, peer.hook_address, key)

        sender = Account.from_key(key).address
        calldata = "0x" + hook.encode("syncCrossChainSpendWithSignature", proof.to_tuple(), signature).hex()
        tx = {"from": sender, "to": peer.hook_address, "data": calldata}

        rpc.call("eth_call", [tx, "latest"])
        gas = int(rpc.call("eth_estimateGas", [tx]), 16)

        signed_tx = Account.sign_transaction({
            **rpc.fee_fields(),
            "chainId": dest_chain_id,
            "to": peer.hook_address,
            "data": calldata,
            "value": 0,
            "nonce": int(rpc.call("eth_getTransactionCount", [sender, "pending"]), 16),
            "gas": int(gas * GAS_MARGIN) + GAS_HEADROOM,
        }, key)

        receipt = rpc.send_raw("0x" + bytes(signed_tx.raw_transaction).hex())
        return {
            "dest_chain_id": dest_chain_id,
            "network": peer.network_name,
            "status": "success",
            "tx_hash": receipt["transactionHash"],
            "nonce": nonce,
            "amount_usd": amount_usd,
        }

    def sync_across_all_peers(
        self,
        account: str,
        source_chain_id: int,
        amount_usd: float,
        signer_key: str | bytes | None = None,
    ) -> list[dict[str, Any]]:
        """Broadcasts spend proof to all registered peer chains except the source chain."""
        results = []
        for chain_id in list(self.peer_chains.keys()):
            if chain_id == source_chain_id:
                continue
            try:
                res = self.relay_spend_to_chain(
                    dest_chain_id=chain_id,
                    account=account,
                    source_chain_id=source_chain_id,
                    amount_usd=amount_usd,
                    signer_key=signer_key,
                )
                results.append(res)
            except Exception as e:
                logger.error("Failed to relay spend to chain %s: %s", chain_id, e)
                results.append({
                    "dest_chain_id": chain_id,
                    "status": "failed",
                    "error": str(e),
                })
        return results


__all__ = [
    "CrossChainBridgeRelayer",
    "CrossChainSpendProof",
    "PeerChainConfig",
    "compute_proof_message_hash",
    "sign_spend_proof",
]

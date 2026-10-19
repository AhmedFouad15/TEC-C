"""Minimal Ethereum JSON-RPC client on the standard library (no web3.py: fewer dependencies to trust)."""

from __future__ import annotations

import itertools
import json
import time
import urllib.request
from typing import Any

from eth_account import Account


GAS_MARGIN = 1.25  # node estimates can fall short for nested calls (63/64 rule); unused gas is not charged
GAS_HEADROOM = 30_000


class RpcError(RuntimeError):
    def __init__(self, code: int, message: str, data: str | None = None) -> None:
        super().__init__(f"{message} (code {code})")
        self.code, self.message, self.data = code, message, data


def _revert_data(err: dict[str, Any]) -> str | None:
    data = err.get("data")
    if isinstance(data, dict):  # some nodes nest it
        data = data.get("data")
    return data if isinstance(data, str) and data.startswith("0x") else None


class Rpc:
    def __init__(self, url: str, timeout_s: float = 10.0) -> None:
        if not url.startswith(("http://127.0.0.1", "http://localhost", "https://")):
            raise ValueError("RPC must be local (http://127.0.0.1 / localhost) or https")
        self.url, self.timeout_s = url, timeout_s
        self._ids = itertools.count(1)

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        body = json.dumps({"jsonrpc": "2.0", "id": next(self._ids), "method": method, "params": params or []}).encode()
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Tec-C/1.0",
        }
        req = urllib.request.Request(self.url, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310 — URL scheme checked above
            payload = json.loads(resp.read())
        if "error" in payload:
            err = payload["error"]
            raise RpcError(err.get("code", -1), err.get("message", "rpc error"), _revert_data(err))
        return payload["result"]

    def chain_id(self) -> int:
        return int(self.call("eth_chainId"), 16)

    def block_timestamp(self, block: str = "latest") -> int:
        return int(self.call("eth_getBlockByNumber", [block, False])["timestamp"], 16)

    def wait(self, tx_hash: str, timeout_s: float = 120.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        is_local = "127.0.0.1" in self.url or "localhost" in self.url
        poll_interval = 0.05 if is_local else 2.0
        while time.monotonic() < deadline:
            receipt = self.call("eth_getTransactionReceipt", [tx_hash])
            if receipt is not None:
                return receipt
            time.sleep(poll_interval)
        raise TimeoutError(f"no receipt for {tx_hash}")

    def send_unlocked(self, tx: dict[str, Any]) -> dict[str, Any]:
        """eth_sendTransaction from a node-managed (Anvil dev) account. Reverts surface as RpcError before mining.

        The gas limit is set explicitly with a margin: the node's own estimate can come out a few hundred gas short
        for nested calls (63/64 gas forwarding into the hook), and the transaction then reverts out of gas."""
        if "gas" not in tx:
            estimate = int(self.call("eth_estimateGas", [tx]), 16)
            tx = {**tx, "gas": hex(int(estimate * GAS_MARGIN) + GAS_HEADROOM)}
        receipt = self.wait(self.call("eth_sendTransaction", [tx]))
        if receipt["status"] != "0x1":
            self._raise_revert(tx, receipt)
        return receipt

    def _raise_revert(self, tx: dict[str, Any], receipt: dict[str, Any]) -> None:
        """Replay the call at the parent block to recover the revert data, then raise it."""
        parent = hex(int(receipt["blockNumber"], 16) - 1)
        replay = {k: v for k, v in tx.items() if k in ("from", "to", "data", "value")}
        try:
            self.call("eth_call", [replay, parent])
        except RpcError as exc:
            raise RpcError(exc.code, f"transaction {receipt['transactionHash']} reverted: {exc.message}", exc.data) from None
        raise RpcError(-32000, f"transaction {receipt['transactionHash']} reverted")

    def fee_fields(self) -> dict[str, Any]:
        """EIP-1559 fees when the chain has a base fee, else a legacy (EIP-155) gas price.

        Ethereum, Arbitrum and Anvil use EIP-1559; FISCO BCOS's web3 RPC and other consortium chains may not.
        """
        gas_price = int(self.call("eth_gasPrice"), 16)
        block = self.call("eth_getBlockByNumber", ["latest", False]) or {}
        if block.get("baseFeePerGas") is not None:
            base_fee = int(block["baseFeePerGas"], 16)
            chain_id = self.chain_id()
            if chain_id == 11155111:  # Ethereum Sepolia: ensure >= 1.5 gwei priority fee for swift block inclusion
                priority_fee = max(gas_price, 1_500_000_000)
                max_fee = max(base_fee * 2 + priority_fee, 3_000_000_000)
                return {"type": 2, "maxFeePerGas": max_fee, "maxPriorityFeePerGas": priority_fee}
            return {"type": 2, "maxFeePerGas": max(gas_price * 2, 1), "maxPriorityFeePerGas": min(gas_price, 10**9)}
        return {"gasPrice": gas_price}

    def send_signed(self, tx: dict[str, Any], private_key: bytes | str, gas_margin: float = 1.25) -> dict[str, Any]:
        """Sign locally and send: works on any EVM JSON-RPC node (testnets, L2s, FISCO BCOS web3 RPC).
        `tx` holds to/data/value (hex value, as for eth_sendTransaction); nonce, gas, fees and chain id are filled."""
        signer = Account.from_key(private_key)
        call = {"from": signer.address, **{k: tx[k] for k in ("to", "data", "value") if k in tx}}
        try:
            gas = int(self.call("eth_estimateGas", [call]), 16)
        except Exception:
            gas = 12_000_000
        # Ethereum block gas limit is 30,000,000. Never exceed 25,000,000.
        gas_limit = min(int(gas * gas_margin) + GAS_HEADROOM, 25_000_000)
        full: dict[str, Any] = {
            **self.fee_fields(),
            "chainId": self.chain_id(),
            "nonce": int(self.call("eth_getTransactionCount", [signer.address, "pending"]), 16),
            "gas": gas_limit,
            "data": tx.get("data", "0x"),
            "value": int(tx.get("value", "0x0"), 16),
        }
        if tx.get("to"):
            full["to"] = tx["to"]
        signed = Account.sign_transaction(full, private_key)
        receipt = self.wait(self.call("eth_sendRawTransaction", ["0x" + bytes(signed.raw_transaction).hex()]))
        if receipt["status"] != "0x1":
            self._raise_revert(call, receipt)
        return receipt

    def send(self, tx: dict[str, Any], private_key: bytes | str | None = None) -> dict[str, Any]:
        """Signed with `private_key` when given (real networks), else from a node-managed dev account (Anvil)."""
        return self.send_signed(tx, private_key) if private_key is not None else self.send_unlocked(tx)

    def send_raw(self, raw_tx: str) -> dict[str, Any]:
        receipt = self.wait(self.call("eth_sendRawTransaction", [raw_tx]))
        if receipt["status"] != "0x1":
            raise RpcError(-32000, f"transaction {receipt['transactionHash']} reverted")
        return receipt

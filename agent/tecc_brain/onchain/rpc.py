"""Minimal Ethereum JSON-RPC client on the standard library (no web3.py: fewer dependencies to trust)."""

from __future__ import annotations

import itertools
import json
import time
import urllib.request
from typing import Any


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
        req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"})
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

    def wait(self, tx_hash: str, timeout_s: float = 30.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            receipt = self.call("eth_getTransactionReceipt", [tx_hash])
            if receipt is not None:
                return receipt
            time.sleep(0.05)
        raise TimeoutError(f"no receipt for {tx_hash}")

    def send_unlocked(self, tx: dict[str, Any]) -> dict[str, Any]:
        """eth_sendTransaction from a node-managed (Anvil dev) account. Reverts surface as RpcError before mining."""
        receipt = self.wait(self.call("eth_sendTransaction", [tx]))
        if receipt["status"] != "0x1":
            raise RpcError(-32000, f"transaction {receipt['transactionHash']} reverted")
        return receipt

    def send_raw(self, raw_tx: str) -> dict[str, Any]:
        receipt = self.wait(self.call("eth_sendRawTransaction", [raw_tx]))
        if receipt["status"] != "0x1":
            raise RpcError(-32000, f"transaction {receipt['transactionHash']} reverted")
        return receipt

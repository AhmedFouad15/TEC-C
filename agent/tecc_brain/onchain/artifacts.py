"""Load Member 1's compiled contracts (forge `out/`) and encode/decode calls with eth_abi."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from eth_abi import decode, encode
from eth_utils import keccak, to_checksum_address

from tecc_brain.onchain.rpc import Rpc, RpcError

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = REPO_ROOT / "contracts"  # Member 1's Foundry project
NATIVE_ETH = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"


def out_dir() -> Path:
    return Path(os.environ.get("TECC_FOUNDRY_OUT", CONTRACTS_DIR / "out"))


@lru_cache(maxsize=None)
def _artifact(name: str) -> dict[str, Any]:
    path = out_dir() / f"{name}.sol" / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run `forge build` in {CONTRACTS_DIR}")
    return json.loads(path.read_text(encoding="utf-8"))


def abi_type(param: dict[str, Any]) -> str:
    t = param["type"]
    if t.startswith("tuple"):
        inner = ",".join(abi_type(c) for c in param["components"])
        return f"({inner}){t[len('tuple'):]}"
    return t


def _signature(entry: dict[str, Any]) -> str:
    return f"{entry['name']}({','.join(abi_type(i) for i in entry['inputs'])})"


class Contract:
    def __init__(self, name: str, abi: list[dict[str, Any]], bytecode: str, address: str | None = None) -> None:
        self.name, self.abi, self.bytecode = name, abi, bytecode
        self.address = to_checksum_address(address) if address else None
        self.errors = {keccak(text=_signature(e))[:4]: e for e in abi if e["type"] == "error"}
        self.events = {keccak(text=_signature(e)): e for e in abi if e["type"] == "event"}

    @classmethod
    def load(cls, name: str, address: str | None = None) -> "Contract":
        art = _artifact(name)
        return cls(name, art["abi"], art["bytecode"]["object"], address)

    def at(self, address: str) -> "Contract":
        return Contract(self.name, self.abi, self.bytecode, address)

    def _fn(self, name: str, nargs: int) -> dict[str, Any]:
        matches = [e for e in self.abi if e.get("type") == "function" and e["name"] == name and len(e["inputs"]) == nargs]
        if len(matches) != 1:
            raise ValueError(f"{self.name}.{name} with {nargs} args not found (or ambiguous)")
        return matches[0]

    def encode(self, name: str, *args: Any) -> bytes:
        fn = self._fn(name, len(args))
        return keccak(text=_signature(fn))[:4] + encode([abi_type(i) for i in fn["inputs"]], list(args))

    def call(self, rpc: Rpc, name: str, *args: Any, sender: str | None = None, value: int = 0) -> tuple[Any, ...]:
        assert self.address, "contract has no address"
        tx: dict[str, Any] = {"to": self.address, "data": "0x" + self.encode(name, *args).hex()}
        if sender:
            tx["from"] = sender
        if value:
            tx["value"] = hex(value)
        out = rpc.call("eth_call", [tx, "latest"])
        fn = self._fn(name, len(args))
        return tuple(decode([abi_type(o) for o in fn["outputs"]], bytes.fromhex(out[2:])))

    def transact(self, rpc: Rpc, name: str, *args: Any, sender: str, value: int = 0) -> dict[str, Any]:
        assert self.address, "contract has no address"
        tx = {"from": sender, "to": self.address, "data": "0x" + self.encode(name, *args).hex()}
        if value:
            tx["value"] = hex(value)
        return rpc.send_unlocked(tx)

    def deploy(self, rpc: Rpc, sender: str, *args: Any) -> "Contract":
        ctor = next((e for e in self.abi if e["type"] == "constructor"), {"inputs": []})
        data = self.bytecode + encode([abi_type(i) for i in ctor["inputs"]], list(args)).hex()
        receipt = rpc.send_unlocked({"from": sender, "data": data})
        return self.at(receipt["contractAddress"])

    def decode_error(self, data: str | None) -> str | None:
        """Custom error → "Name(arg, …)"; also Error(string). None when unknown."""
        if not data or len(data) < 10:
            return None
        raw = bytes.fromhex(data[2:])
        if raw[:4] == keccak(text="Error(string)")[:4]:
            return f"Error({decode(['string'], raw[4:])[0]!r})"
        entry = self.errors.get(raw[:4])
        if entry is None:
            return None
        values = decode([abi_type(i) for i in entry["inputs"]], raw[4:])
        return f"{entry['name']}({', '.join(str(v) for v in values)})"

    def decode_logs(self, logs: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
        """(event name, args, raw log) for logs this contract emitted."""
        out = []
        for log in logs:
            if self.address and log["address"].lower() != self.address.lower():
                continue
            topic0 = bytes.fromhex(log["topics"][0][2:]) if log["topics"] else b""
            event = self.events.get(topic0)
            if event is None:
                continue
            indexed = [i for i in event["inputs"] if i.get("indexed")]
            plain = [i for i in event["inputs"] if not i.get("indexed")]
            args: dict[str, Any] = {}
            for param, topic in zip(indexed, log["topics"][1:]):
                args[param["name"]] = decode([abi_type(param)], bytes.fromhex(topic[2:]))[0]
            values = decode([abi_type(p) for p in plain], bytes.fromhex(log["data"][2:])) if plain else ()
            args.update({p["name"]: v for p, v in zip(plain, values)})
            out.append((event["name"], args, log))
        return out


def revert_reason(err: RpcError, *contracts: Contract) -> str:
    for contract in contracts:
        decoded = contract.decode_error(err.data)
        if decoded:
            return decoded
    return err.message

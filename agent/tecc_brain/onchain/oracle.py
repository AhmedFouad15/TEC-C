"""Chainlink On-Chain Oracle Client for Tec-C.

Queries live Chainlink Price Feed aggregators directly via free JSON-RPC `eth_call` to `latestRoundData()`.
Requires zero API keys and incurs zero gas costs.
Verified contract addresses are loaded from `shared/chainlink_feeds.json`.
"""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any
import urllib.request

from eth_abi import decode
from pydantic import BaseModel, Field

from tecc_brain.onchain.rpc import Rpc

FEEDS_FILE = Path(__file__).resolve().parents[3] / "shared" / "chainlink_feeds.json"
LATEST_ROUND_DATA_SELECTOR = "0xfeaf968c"


class ChainlinkRoundData(BaseModel):
    symbol: str
    price_usd: float
    raw_answer: int
    decimals: int = 8
    round_id: int
    updated_at: int
    answered_in_round: int
    chain_id: int
    feed_address: str
    is_valid: bool = True


class ChainlinkFeedConfig(BaseModel):
    address: str
    decimals: int = 8
    tokenAddress: str
    symbol: str


class ChainlinkNetworkConfig(BaseModel):
    chainId: int
    rpcUrl: str
    rpcUrls: list[str] = Field(default_factory=list)
    feeds: dict[str, ChainlinkFeedConfig] = Field(default_factory=dict)


class ChainlinkOracleClient:
    def __init__(self, config_file: Path = FEEDS_FILE, cache_ttl_seconds: float = 30.0) -> None:
        self.config_file = config_file
        self.cache_ttl = cache_ttl_seconds
        self._cache: dict[str, tuple[float, ChainlinkRoundData]] = {}
        self._networks: dict[str, ChainlinkNetworkConfig] = {}
        self.reload()

    def reload(self) -> None:
        if not self.config_file.exists():
            return
        data = json.loads(self.config_file.read_text(encoding="utf-8"))
        for net_name, net_data in data.items():
            if net_name.startswith("_"):
                continue
            self._networks[net_name] = ChainlinkNetworkConfig.model_validate(net_data)

    def _get_network_for_chain(self, chain_id: int) -> tuple[str, ChainlinkNetworkConfig] | tuple[None, None]:
        for name, config in self._networks.items():
            if config.chainId == chain_id:
                return name, config
        return None, None

    def get_feed_address(self, symbol: str, chain_id: int = 1) -> str | None:
        _, net = self._get_network_for_chain(chain_id)
        if not net:
            return None
        pair = f"{symbol.upper()}/USD"
        feed = net.feeds.get(pair) or net.feeds.get(symbol.upper())
        return feed.address if feed else None

    def fetch_round_data(
        self,
        symbol: str,
        chain_id: int = 1,
        rpc_url: str | None = None,
        max_staleness_seconds: int = 86400,
    ) -> ChainlinkRoundData:
        cache_key = f"{chain_id}:{symbol.upper()}"
        now = time.time()
        if cache_key in self._cache:
            ts, cached = self._cache[cache_key]
            if now - ts < self.cache_ttl:
                return cached

        net_name, net = self._get_network_for_chain(chain_id)
        if not net:
            raise ValueError(f"No Chainlink feeds configured for chain_id {chain_id}")

        pair = f"{symbol.upper()}/USD"
        feed_config = net.feeds.get(pair) or net.feeds.get(symbol.upper())
        if not feed_config:
            raise ValueError(f"No Chainlink feed found for symbol {symbol} on chain {chain_id}")

        feed_address = feed_config.address
        endpoints = [rpc_url] if rpc_url else (net.rpcUrls or [net.rpcUrl])

        last_error: Exception | None = None
        raw_result: str | None = None

        for endpoint in endpoints:
            try:
                payload = json.dumps({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "eth_call",
                    "params": [{"to": feed_address, "data": LATEST_ROUND_DATA_SELECTOR}, "latest"],
                }).encode("utf-8")
                req = urllib.request.Request(
                    endpoint,
                    data=payload,
                    headers={"Content-Type": "application/json", "User-Agent": "Tec-C-Oracle/1.0"},
                )
                with urllib.request.urlopen(req, timeout=7.0) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    if "result" in res_json and res_json["result"] and res_json["result"] != "0x":
                        raw_result = res_json["result"]
                        break
                    if "error" in res_json:
                        raise RuntimeError(f"RPC error from {endpoint}: {res_json['error']}")
            except Exception as e:
                last_error = e
                continue

        if raw_result is None:
            raise RuntimeError(f"Failed to fetch Chainlink feed for {symbol} on chain {chain_id}: {last_error}")

        raw_bytes = bytes.fromhex(raw_result[2:])
        round_id, answer, _started_at, updated_at, answered_in_round = decode(
            ["uint80", "int256", "uint256", "uint256", "uint80"], raw_bytes
        )

        if answer <= 0:
            raise ValueError(f"Chainlink returned non-positive price for {symbol}: {answer}")
        if updated_at == 0 or answered_in_round < round_id:
            raise ValueError(f"Incomplete round in Chainlink feed for {symbol}")

        is_valid = (now - updated_at <= max_staleness_seconds) if updated_at > 0 else False
        price_usd = float(answer) / (10 ** feed_config.decimals)

        data = ChainlinkRoundData(
            symbol=symbol.upper(),
            price_usd=price_usd,
            raw_answer=int(answer),
            decimals=feed_config.decimals,
            round_id=int(round_id),
            updated_at=int(updated_at),
            answered_in_round=int(answered_in_round),
            chain_id=chain_id,
            feed_address=feed_address,
            is_valid=is_valid,
        )
        self._cache[cache_key] = (now, data)
        return data

    def get_price_usd(self, symbol: str, chain_id: int = 1) -> float:
        return self.fetch_round_data(symbol, chain_id=chain_id).price_usd


_GLOBAL_ORACLE_CLIENT: ChainlinkOracleClient | None = None


def get_chainlink_oracle() -> ChainlinkOracleClient:
    global _GLOBAL_ORACLE_CLIENT
    if _GLOBAL_ORACLE_CLIENT is None:
        _GLOBAL_ORACLE_CLIENT = ChainlinkOracleClient()
    return _GLOBAL_ORACLE_CLIENT


__all__ = [
    "ChainlinkFeedConfig",
    "ChainlinkNetworkConfig",
    "ChainlinkOracleClient",
    "ChainlinkRoundData",
    "get_chainlink_oracle",
]

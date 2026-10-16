"""Local privacy sieve: balances, amounts, addresses and identities are replaced by tokens before any text or
payload leaves the machine for a cloud model, and restored locally afterwards (Prof. Qiang Yang's concern).
"""

from __future__ import annotations

import re
from typing import Any

# Order matters: DIDs contain addresses, so they are masked first. Everything fails closed: over-masking only costs
# the model a little context, under-masking leaks a balance or an identity.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("DID", re.compile(r"did:[a-z0-9]+:[\w:.\-]+", re.IGNORECASE)),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    # EVM addresses and tx hashes, any case, also when split by spaces.
    ("ADDR", re.compile(r"0[xX](?:[0-9a-fA-F]{64}|[0-9a-fA-F]{40}|(?:\s?[0-9a-fA-F]{4}){10})(?![0-9a-fA-F])")),
    ("ENS", re.compile(r"\b[a-zA-Z0-9][a-zA-Z0-9-]*\.eth\b")),
    # Other chains' addresses (base58 / bech32): long alphanumeric runs mixing letters and digits.
    ("ADDR", re.compile(r"\b(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{26,}\b")),
    # Every number, even glued to a word ("10ETH", "USDC1500"); k/m suffix kept with it only when standalone.
    ("AMT", re.compile(r"\d+(?:[.,]\d+)*(?:[kKmM](?![A-Za-z]))?")),
)
_TOKEN = re.compile(r"<(?:DID|EMAIL|ADDR|ENS|AMT)_\d+>")
# Numbers under these payload keys are structural, not private; every other number is masked.
SAFE_NUMERIC_KEYS = frozenset({"tier", "risk_tier", "horizon_days", "decimals", "chain_id", "chainid"})


class _Masker:
    def __init__(self) -> None:
        self.vault: dict[str, str] = {}
        self._tokens: dict[str, str] = {}
        self._counts: dict[str, int] = {}

    def token(self, kind: str, original: str) -> str:
        if original not in self._tokens:
            self._counts[kind] = self._counts.get(kind, 0) + 1
            token = f"<{kind}_{self._counts[kind]}>"
            self._tokens[original] = token
            self.vault[token] = original
        return self._tokens[original]

    def text(self, text: str) -> str:
        for kind, pattern in _PATTERNS:
            # Never re-mask inside tokens produced by an earlier pattern.
            parts = _TOKEN.split(text)
            tokens = _TOKEN.findall(text)
            parts = [pattern.sub(lambda m, kind=kind: self.token(kind, m.group(0)), part) for part in parts]
            text = "".join(p + (tokens[i] if i < len(tokens) else "") for i, p in enumerate(parts))
        return text

    def payload(self, value: Any, key: str = "") -> Any:
        if isinstance(value, dict):
            return {self.text(str(k)) if isinstance(k, str) else k: self.payload(v, str(k)) for k, v in value.items()}
        if isinstance(value, list):
            return [self.payload(v, key) for v in value]
        if isinstance(value, (int, float)) and not isinstance(value, bool) and key.lower() not in SAFE_NUMERIC_KEYS:
            return self.token("AMT", repr(value))
        if isinstance(value, str):
            return self.text(value)
        return value


def mask(text: str) -> tuple[str, dict[str, str]]:
    masker = _Masker()
    return masker.text(text), masker.vault


def mask_payload(payload: Any) -> tuple[Any, dict[str, str]]:
    masker = _Masker()
    return masker.payload(payload), masker.vault


def restore(text: str, vault: dict[str, str]) -> str:
    for token in sorted(vault, key=len, reverse=True):  # <AMT_11> before <AMT_1>
        text = text.replace(token, vault[token])
    return text

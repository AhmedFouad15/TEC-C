"""Local privacy sieve: balances, amounts, addresses and identities are replaced by tokens before any text or
payload leaves the machine for a cloud model, and restored locally afterwards (Prof. Qiang Yang's concern).
"""

from __future__ import annotations

import re
from typing import Any

# Order matters: DIDs contain addresses, so they are masked first.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("DID", re.compile(r"did:[a-z0-9]+:[\w:.\-]+", re.IGNORECASE)),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("ADDR", re.compile(r"\b0x[0-9a-fA-F]{40}\b")),
    ("ENS", re.compile(r"\b[a-zA-Z0-9][a-zA-Z0-9-]*\.eth\b")),
    # Numbers not glued to a word/token ("<ADDR_1>", "1Y", "v3"); "$" stays outside so the currency is still readable.
    ("AMT", re.compile(r"(?<![\w.<])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:[km])?(?![\w>])", re.IGNORECASE)),
)
_SENSITIVE_KEY = re.compile(r"balance|amount|value|nav|usd|price|radius|spent", re.IGNORECASE)


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
            text = pattern.sub(lambda m, kind=kind: self.token(kind, m.group(0)), text)
        return text

    def payload(self, value: Any, key: str = "") -> Any:
        if isinstance(value, dict):
            return {k: self.payload(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [self.payload(v, key) for v in value]
        if isinstance(value, (int, float)) and not isinstance(value, bool) and _SENSITIVE_KEY.search(key):
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

"""Prompt-injection firewall: runs on every piece of text the Brain reads — user requests, LLM output, review notes.

Text can never add recipients, raise limits or override the Brain's rules. This is defence in depth: even if
this layer were bypassed, the on-chain TetherGuardHook still reverts unauthorised targets and over-radius spends.
Patterns are plain module constants so they can be audited.
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum

from pydantic import BaseModel


class Threat(str, Enum):
    # Declaration order is the report order.
    OVERRIDE_INSTRUCTION = "OVERRIDE_INSTRUCTION"
    LIMIT_CHANGE = "LIMIT_CHANGE"
    UNLIMITED_APPROVAL = "UNLIMITED_APPROVAL"
    DRAIN = "DRAIN"
    UNKNOWN_RECIPIENT = "UNKNOWN_RECIPIENT"


THREAT_TEXT: dict[Threat, str] = {
    Threat.OVERRIDE_INSTRUCTION: "Tries to override the Brain's instructions or rules.",
    Threat.LIMIT_CHANGE: "Tries to change a spending limit, whitelist or safety setting through text.",
    Threat.UNLIMITED_APPROVAL: "Asks for an unlimited token approval.",
    Threat.DRAIN: "Asks to move all funds at once.",
    Threat.UNKNOWN_RECIPIENT: "Sends funds to an address that is not on your approved list.",
}

# Zero-width, joiner and bidi control characters used to split keywords and hide intent.
_INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤﻿­]")

PATTERNS: dict[Threat, tuple[str, ...]] = {
    Threat.OVERRIDE_INSTRUCTION: (
        r"\boverride\b",
        r"\bignore\b(?:\W+\w+){0,3}?\W+(?:instructions?|rules?|prompts?|guardrails?)\b",
        r"\bdisregard\b(?:\W+\w+){0,3}?\W+(?:instructions?|rules?|limits?)\b",
        r"\bsystem prompt\b",
        r"\byou are now\b",
        r"\bdeveloper mode\b",
        r"\bjailbreak\b",
        r"\bact as (?:an? )?(?:admin|owner|root)\b",
    ),
    Threat.LIMIT_CHANGE: (
        r"\b(?:set|raise|increase|lift|remove|disable|bypass|turn off|change|double|unlock|extend)\b"
        r"(?:\W+\w+){0,5}?\W+(?:tether|radius|limits?|whitelist|cap|heartbeat|guard|hook|ceiling|quota|tier)\b",
    ),
    Threat.UNLIMITED_APPROVAL: (
        r"\b(?:unlimited|infinite|max(?:imum)?|uint256)\s+(?:token\s+)?(?:approvals?|allowances?)\b",
        r"\bapprove\s+(?:an?\s+)?(?:unlimited|infinite|max(?:imum)?)\b",
    ),
    Threat.DRAIN: (
        r"\bdrain\b",
        r"\ball\s+(?:of\s+)?(?:my\s+|the\s+|our\s+)?(?:funds|money|assets|balances?|treasury|holdings)\b",
        r"\bentire\s+(?:treasury|balance|portfolio|vault|wallet)\b",
        r"\b(?:send|move|transfer|withdraw)\s+everything\b",
        r"\bempty\s+(?:the|my|our)\s+(?:vault|wallet|treasury|account)\b",
    ),
}

_HEX_ADDRESS = re.compile(r"\b0x[0-9a-f]{40}\b")
_PSEUDO_ADDRESS = re.compile(r"\b0x[0-9a-z]{2,}\b")  # e.g. "0xhacker": still an attempt to name a recipient
_ENS = re.compile(r"\b[a-z0-9][a-z0-9-]*\.eth\b")


class FirewallVerdict(BaseModel):
    allowed: bool
    threats: list[Threat]
    recipients: list[str]
    normalized: str

    def explain(self) -> list[str]:
        return [THREAT_TEXT[t] for t in self.threats]


def normalize(text: str) -> str:
    """NFKC (folds full-width and other look-alikes), drop invisible characters, collapse whitespace."""
    folded = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", _INVISIBLE.sub("", folded)).strip()


def find_recipients(normalized_lower: str) -> list[str]:
    found = _HEX_ADDRESS.findall(normalized_lower) + _PSEUDO_ADDRESS.findall(normalized_lower) + _ENS.findall(normalized_lower)
    return list(dict.fromkeys(found))


def scan(text: str, allowed_recipients: frozenset[str] = frozenset()) -> FirewallVerdict:
    normalized = normalize(text)
    lower = normalized.lower()
    threats = {threat for threat, patterns in PATTERNS.items() if any(re.search(p, lower) for p in patterns)}

    allowed_lower = {r.lower() for r in allowed_recipients}
    recipients = find_recipients(lower)
    if any(r not in allowed_lower for r in recipients):
        threats.add(Threat.UNKNOWN_RECIPIENT)

    ordered = [t for t in Threat if t in threats]
    return FirewallVerdict(allowed=not ordered, threats=ordered, recipients=recipients, normalized=normalized)

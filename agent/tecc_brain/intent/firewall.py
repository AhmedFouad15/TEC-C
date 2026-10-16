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
    OBFUSCATION = "OBFUSCATION"


THREAT_TEXT: dict[Threat, str] = {
    Threat.OVERRIDE_INSTRUCTION: "Tries to override the Brain's instructions or rules.",
    Threat.LIMIT_CHANGE: "Tries to change a spending limit, whitelist or safety setting through text.",
    Threat.UNLIMITED_APPROVAL: "Asks for an unlimited token approval.",
    Threat.DRAIN: "Asks to move all funds at once.",
    Threat.UNKNOWN_RECIPIENT: "Sends funds to an address that is not on your approved list.",
    Threat.OBFUSCATION: "Hides words with look-alike letters from other alphabets or encoded text.",
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

SQUASHED = {
    "OVERRIDE_INSTRUCTION": (r"override", r"jailbreak", r"developermode", r"systemprompt",
                             r"ignore(?:all|any)?(?:previous|prior|above|earlier)?(?:instructions?|rules?|prompts?)"),
    "DRAIN": (r"drain", r"(?:send|move|transfer)everything"),
    "UNLIMITED_APPROVAL": (r"(?:unlimited|infinite)(?:token)?(?:approv|allowanc)",),
}

_HEX_ADDRESS = re.compile(r"\b0x[0-9a-f]{40}\b")
_PSEUDO_ADDRESS = re.compile(r"\b0x[0-9a-z]{2,}\b")  # e.g. "0xhacker": still an attempt to name a recipient
_ENS = re.compile(r"\b[a-z0-9][a-z0-9-]*\.eth\b")
_DID = re.compile(r"did:[a-z0-9]+:[\w:.\-]+")

# Cyrillic/Greek letters that look Latin. NFKC does not fold these, so "оverride" (Cyrillic о) would slip past the
# patterns while a language model still reads "override". Fold them before matching, and flag mixed-script words.
CONFUSABLES = str.maketrans({
    "а": "a", "в": "b", "е": "e", "ё": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p", "с": "c",
    "т": "t", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "ӏ": "l", "ԛ": "q", "ԝ": "w",
    "α": "a", "β": "b", "ε": "e", "η": "n", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t",
    "υ": "u", "χ": "x", "ω": "w",
    # small capitals
    "ᴀ": "a", "ʙ": "b", "ᴄ": "c", "ᴅ": "d", "ᴇ": "e", "ғ": "f", "ɢ": "g", "ʜ": "h", "ɪ": "i", "ᴊ": "j", "ᴋ": "k",
    "ʟ": "l", "ᴍ": "m", "ɴ": "n", "ᴏ": "o", "ᴘ": "p", "ʀ": "r", "ꜱ": "s", "ᴛ": "t", "ᴜ": "u", "ᴠ": "v", "ᴡ": "w",
    "ʏ": "y", "ᴢ": "z",
})
# IPA, phonetic extensions and Latin extended-D letters never belong in a wallet request.
_EXOTIC_LATIN = re.compile(r"[\u0250-\u02af\u1d00-\u1dbf\ua700-\ua7ff]")
_LATIN = re.compile(r"[a-z]")
# Scripts that legitimately sit next to Latin in a request (Chinese/Japanese/Korean) are not look-alikes.
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]")

# Second pass on a "squashed" copy (punctuation/spaces removed, leetspeak folded) so "d r a i n", "o-v-e-r-r-i-d-e"
# or "0verr1de" cannot hide a keyword that a language model would still read. Only distinctive phrases are used here.
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t"})
_SQUASHED_HEX_ADDRESS = re.compile(r"0x[0-9a-f]{40}")
# Long base64-like blobs can carry encoded instructions for a model to decode.
_ENCODED_BLOB = re.compile(r"(?<![0-9a-zA-Z])(?!0x)[A-Za-z0-9+/]{24,}={0,2}(?![0-9a-zA-Z])")


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


def _is_mixed_script(lower: str) -> bool:
    """A word that mixes ASCII letters with letters from another alphabet (Cyrillic, Greek, small caps, IPA …)."""
    for word in re.findall(r"\w+", lower):
        if not _LATIN.search(word):
            continue
        for ch in word:
            if ch.isalpha() and ord(ch) > 0x24F and not _CJK.match(ch):
                return True
    return False


def _squashed_threats(folded: str) -> tuple[set["Threat"], list[str]]:
    squashed = re.sub(r"[^a-z0-9]", "", folded)
    addresses = _SQUASHED_HEX_ADDRESS.findall(squashed)
    leet = squashed.translate(_LEET)
    threats = {Threat(name) for name, patterns in SQUASHED.items() if any(re.search(p, leet) for p in patterns)}
    return threats, addresses


def find_recipients(normalized_lower: str, known_identities: frozenset[str] = frozenset()) -> list[str]:
    """Addresses, pseudo-addresses ("0xhacker"), ENS names and unknown DIDs. Only the user's own known DIDs are exempt —
    an arbitrary DID could be used to smuggle a payee address past the filter."""
    known = {k.lower() for k in known_identities}
    dids = _DID.findall(normalized_lower)
    for did in dids:
        normalized_lower = normalized_lower.replace(did, " ")
    found = [d for d in dids if d not in known]
    found += _HEX_ADDRESS.findall(normalized_lower) + _PSEUDO_ADDRESS.findall(normalized_lower) + _ENS.findall(normalized_lower)
    return list(dict.fromkeys(found))


def scan(
    text: str,
    allowed_recipients: frozenset[str] = frozenset(),
    known_identities: frozenset[str] = frozenset(),
) -> FirewallVerdict:
    """`normalized` in the verdict is exactly the string that was checked; anything downstream (rule parser, LLM)
    must consume that string, never the raw input, so the filter and the model cannot read different text."""
    normalized = normalize(text)
    lower = normalized.lower()
    folded = lower.translate(CONFUSABLES)
    threats = {threat for threat, patterns in PATTERNS.items() if any(re.search(p, folded) for p in patterns)}
    if _is_mixed_script(lower) or _EXOTIC_LATIN.search(lower) or _ENCODED_BLOB.search(normalized):
        threats.add(Threat.OBFUSCATION)

    allowed_lower = {r.lower() for r in allowed_recipients}
    recipients = find_recipients(folded, known_identities)
    # DIDs are already accounted for above (known ones exempt, unknown ones flagged); drop them before squashing so
    # the address embedded in the user's own DID is not re-detected as a payee.
    squashed_threats, squashed_addresses = _squashed_threats(_DID.sub(" ", folded))
    threats |= squashed_threats
    recipients += [a for a in squashed_addresses if a not in recipients]
    if any(r not in allowed_lower for r in recipients):
        threats.add(Threat.UNKNOWN_RECIPIENT)

    ordered = [t for t in Threat if t in threats]
    return FirewallVerdict(allowed=not ordered, threats=ordered, recipients=recipients, normalized=normalized)

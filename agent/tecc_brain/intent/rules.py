"""Offline, deterministic mandate parser. Always available — the demo never depends on an LLM.

The firewall runs first; refused text is never parsed. Keyword tables are module constants so they can be audited.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from tecc_brain.intent.firewall import FirewallVerdict, scan
from tecc_brain.models import ActionType, Mandate, Portfolio
from tecc_brain.reference import Reference

# Checked in order; the first match wins.
ACTION_PATTERNS: tuple[tuple[ActionType, str], ...] = (
    (ActionType.TRANSFER, r"\b(?:send|transfer|pay)\b"),
    (ActionType.WITHDRAW, r"\b(?:withdraw|redeem|exit|pull out)\b"),
    (ActionType.STAKE, r"\b(?:stake|staking)\b"),
    (ActionType.OPTIMIZE_YIELD, r"\b(?:optimi[sz]e|maximi[sz]e|best yield|earn|grow)\b|\bto work\b"),
    (ActionType.DEPOSIT, r"\b(?:deposit|supply|lend)\b|\bput\b.+\binto\b"),
    (ActionType.OPTIMIZE_YIELD, r"\byields?\b"),
)

ASSET_SYNONYMS: dict[str, str] = {
    "ether": "ETH",
    "bitcoin": "WBTC",
    "btc": "WBTC",
    "usd coin": "USDC",
    "dollars": "USDC",
    "dollar": "USDC",
    "gold": "PAXG",
}

_UNIT_DAYS = {"day": 1.0, "week": 7.0, "month": 365.0 / 12, "year": 365.0}
_HORIZON = re.compile(r"\bfor\s+(\d+(?:\.\d+)?|an?|one)\s+(day|week|month|year)s?\b")
_AMOUNT = re.compile(r"(\$)?\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*([km])?\b")
_RELATIVE = re.compile(r"\b(half|all)\s+(?:of\s+)?my\b")
_AVOID = re.compile(r"\b(?:avoid|no|not|without|except|skip)\s+(\w+)")
_PREFER = re.compile(r"\b(?:into|in|on|via|only|using|with|through)\s+(\w+)")

TRANSFER_OUT_OF_SCOPE = "transfers to external addresses are not supported; the Brain only allocates inside the vault"


class ParseOutcome(BaseModel):
    mandate: Mandate | None
    verdict: FirewallVerdict
    errors: list[str] = Field(default_factory=list)


def _asset_lookup(ref: Reference) -> dict[str, str]:
    lookup = {symbol.lower(): symbol for symbol in ref.assets}
    lookup.update(ASSET_SYNONYMS)
    return lookup


def _find_asset(text: str, ref: Reference) -> str | None:
    best: tuple[int, str] | None = None
    for word, symbol in _asset_lookup(ref).items():
        match = re.search(rf"\b{re.escape(word)}\b", text)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), symbol)
    if best:
        return best[1]
    return "USDC" if "$" in text else None


def _find_amount(text: str) -> float | None:
    for match in _AMOUNT.finditer(text):
        dollar, digits, suffix = match.groups()
        value = float(digits.replace(",", ""))
        value *= {"k": 1e3, "m": 1e6}.get(suffix or "", 1.0)
        return value
    return None


def _horizon_days(text: str) -> tuple[int, str]:
    match = _HORIZON.search(text)
    if not match:
        return 365, text
    count = 1.0 if match.group(1) in ("a", "an", "one") else float(match.group(1))
    days = round(count * _UNIT_DAYS[match.group(2)])
    return max(1, days), text[: match.start()] + text[match.end() :]


def _constraints(text: str, ref: Reference) -> list[str]:
    protocols = {v.protocol for v in ref.venues.values()}
    avoid = [w for w in _AVOID.findall(text) if w in protocols]
    prefer = [w for w in _PREFER.findall(text) if w in protocols and w not in avoid]
    return [f"avoid:{p}" for p in dict.fromkeys(avoid)] + [f"venue:{p}" for p in dict.fromkeys(prefer)]


def parse(
    text: str,
    ref: Reference,
    portfolio: Portfolio | None = None,
    allowed_recipients: frozenset[str] = frozenset(),
    known_identities: frozenset[str] = frozenset(),
) -> ParseOutcome:
    verdict = scan(text, allowed_recipients, known_identities)
    if not verdict.allowed:
        return ParseOutcome(
            mandate=None, verdict=verdict, errors=[f"refused by firewall: {', '.join(t.value for t in verdict.threats)}"]
        )

    lower = verdict.normalized.lower()
    action = next((a for a, pattern in ACTION_PATTERNS if re.search(pattern, lower)), None)
    if action is None:
        return ParseOutcome(mandate=None, verdict=verdict, errors=["no action found"])
    if action == ActionType.TRANSFER:
        return ParseOutcome(mandate=None, verdict=verdict, errors=[TRANSFER_OUT_OF_SCOPE])

    asset = _find_asset(lower, ref)
    if asset is None:
        return ParseOutcome(mandate=None, verdict=verdict, errors=["no asset found"])

    horizon, without_horizon = _horizon_days(lower)
    amount: float | None
    amount_usd: float | None = None
    relative = _RELATIVE.search(without_horizon)
    if relative:
        if portfolio is None:
            return ParseOutcome(mandate=None, verdict=verdict, errors=["'half/all my' needs your portfolio"])
        share = 0.5 if relative.group(1) == "half" else 1.0
        held_usd = sum(p.amount_usd for p in portfolio.positions if p.asset == asset and p.venue_id is None)
        amount_usd = share * held_usd
        amount = amount_usd if ref.assets[asset].peg == "USD" else 0.0
    else:
        amount = _find_amount(without_horizon)
    if amount is None:
        return ParseOutcome(mandate=None, verdict=verdict, errors=["no amount found"])

    mandate = Mandate(
        raw_text=text,
        action=action,
        asset=asset,
        amount=amount,
        amount_usd=amount_usd,
        horizon_days=horizon,
        recipients=[],
        constraints=_constraints(lower, ref),
        parser="rules",
    )
    return ParseOutcome(mandate=mandate, verdict=verdict)

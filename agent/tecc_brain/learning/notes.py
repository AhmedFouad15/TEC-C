"""Morning Review notes → structured preferences. Notes are data, never instructions.

"stop using Curve, I hate IL" becomes {protocol: curve, polarity: −1, factor: c_out_stress}. The note is screened by
the injection firewall first; a refused note teaches nothing. The output schema is closed (known protocols, four
factors, ±1), so a note can never raise a limit, add a recipient or touch the vault.

Rules work offline; an LLM can be plugged in as a `complete(prompt) -> str` callable with the same guards as the
intent parser (screened + masked input, validated output, fallback to rules).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field

from tecc_brain.intent.firewall import Threat, scan
from tecc_brain.intent.parser import LLM_TIMEOUT_S, call_with_timeout
from tecc_brain.intent.prompts import NOTE_PROMPT as PROMPT
from tecc_brain.intent.sieve import mask, restore
from tecc_brain.models import CostFactor, NotePreference
from tecc_brain.reference import Reference

RISK_OFF_FACTOR = 1.05  # "too risky", "be safer" → λ × 1.05
RISK_ON_FACTOR = 0.95  # "be more aggressive", "higher yield" → λ × 0.95
MAX_LLM_PREFERENCES = 5

PROTOCOL_SYNONYMS: dict[str, str] = {
    "paxg": "paxos",
    "gold": "paxos",
    "eigen": "eigenlayer",
    "uni": "uniswap",
    "mmf": "shibor_mmf",
    "money market": "shibor_mmf",
}
NEGATED_POSITIVE = re.compile(r"\b(?:don'?t|do not|didn'?t|never|not|no longer)\s+(?:really\s+)?(?:like|love|want|use|trust)\b")
NEGATIVE_CUES = re.compile(
    r"\b(?:stop|avoid|hate|dislike|never|too risky|scared|bad|lost|worse|worried|terrible|awful|no more|painful|"
    r"annoyed|angry|killing)\b"
)
POSITIVE_CUES = re.compile(r"\b(?:love|like|great|good|keep|perfect|nice|happy|thanks|well done|excellent)\b")
FACTOR_CUES: tuple[tuple[CostFactor, re.Pattern[str]], ...] = (
    ("c_out_stress", re.compile(r"\b(?:il|impermanent loss|exits?|slippage|lock(?:ed|up)?|withdrawals?|withdraw)\b")),
    ("c_in", re.compile(r"\b(?:fees?|gas)\b")),
    ("loss", re.compile(r"\b(?:risk|risky|hacks?|hacked|safe|safer|scary)\b")),
    ("yield", re.compile(r"\b(?:yield|apy|returns?|earn(?:ing)?)\b")),
)
RISK_OFF_CUES = re.compile(r"\b(?:too risky|safer|scared|less risk|too aggressive|careful|nervous)\b")
RISK_ON_CUES = re.compile(r"\b(?:more aggressive|higher yields?|more risk|too conservative|too cautious|bolder)\b")


class NoteOutcome(BaseModel):
    preferences: list[NotePreference] = Field(default_factory=list)
    sentiment: Literal[-1, 0, 1] = 0
    lam_factor: float = 1.0
    refused: bool = False
    threats: list[Threat] = Field(default_factory=list)
    source: Literal["rules", "llm"] = "rules"
    errors: list[str] = Field(default_factory=list)


def _protocols(ref: Reference) -> set[str]:
    return {v.protocol for v in ref.venues.values()}


def _mentioned_protocols(text: str, ref: Reference) -> list[str]:
    names = {p: p for p in _protocols(ref)} | PROTOCOL_SYNONYMS
    hits = []
    for word, protocol in names.items():
        match = re.search(rf"\b{re.escape(word.replace('_', ' '))}\b|\b{re.escape(word)}\b", text)
        if match:
            hits.append((match.start(), protocol))
    return list(dict.fromkeys(p for _, p in sorted(hits)))


def _sentiment(text: str) -> Literal[-1, 0, 1]:
    negated = len(NEGATED_POSITIVE.findall(text))
    rest = NEGATED_POSITIVE.sub(" ", text)
    score = len(POSITIVE_CUES.findall(rest)) - len(NEGATIVE_CUES.findall(rest)) - negated
    return 1 if score > 0 else -1 if score < 0 else 0


def _lam_factor(text: str) -> float:
    off, on = bool(RISK_OFF_CUES.search(text)), bool(RISK_ON_CUES.search(text))
    if off and not on:
        return RISK_OFF_FACTOR
    if on and not off:
        return RISK_ON_FACTOR
    return 1.0


def _rules(text: str, ref: Reference) -> NoteOutcome:
    lower = text.lower()
    sentiment = _sentiment(lower)
    factor = next((name for name, pattern in FACTOR_CUES if pattern.search(lower)), None)
    preferences: list[NotePreference] = []
    if sentiment != 0:
        protocols = _mentioned_protocols(lower, ref)
        preferences = [NotePreference(protocol=p, polarity=sentiment, factor=factor) for p in protocols]
        if not protocols and factor is not None and sentiment < 0:
            preferences = [NotePreference(protocol=None, polarity=-1, factor=factor)]
    return NoteOutcome(preferences=preferences, sentiment=sentiment, lam_factor=_lam_factor(lower))


class _LLMPreference(BaseModel):
    protocol: str | None = None
    polarity: Literal[-1, 1]
    factor: str | None = None


class _LLMNote(BaseModel):
    sentiment: Literal[-1, 0, 1] = 0
    lam: Literal["safer", "bolder"] | None = None
    preferences: list[dict] = Field(default_factory=list)


def _llm(approved: str, ref: Reference, complete: Callable[[str], str], timeout_s: float) -> NoteOutcome:
    masked, vault = mask(approved)
    protocols = sorted(_protocols(ref))
    reply = call_with_timeout(complete, PROMPT.format(protocols=protocols, note=masked), timeout_s)
    match = re.search(r"\{.*\}", reply, re.DOTALL)
    if not match:
        raise ValueError("reply contained no JSON object")
    verdict = scan(restore(match.group(0), vault))
    if not verdict.allowed:
        raise ValueError("model output refused by firewall")
    data = _LLMNote.model_validate(json.loads(match.group(0)))
    factors = {name for name, _ in FACTOR_CUES}
    preferences = []
    for raw in data.preferences[:MAX_LLM_PREFERENCES]:
        try:
            pref = _LLMPreference.model_validate(raw)
        except ValueError:
            continue
        if (pref.protocol is None or pref.protocol in protocols) and (pref.factor is None or pref.factor in factors):
            preferences.append(NotePreference(protocol=pref.protocol, polarity=pref.polarity, factor=pref.factor))  # type: ignore[arg-type]
    lam_factor = {"safer": RISK_OFF_FACTOR, "bolder": RISK_ON_FACTOR, None: 1.0}[data.lam]
    return NoteOutcome(preferences=preferences, sentiment=data.sentiment, lam_factor=lam_factor, source="llm")


def parse_note(
    text: str,
    ref: Reference,
    complete: Callable[[str], str] | None = None,
    timeout_s: float = LLM_TIMEOUT_S,
) -> NoteOutcome:
    verdict = scan(text)
    if not verdict.allowed:
        return NoteOutcome(refused=True, threats=verdict.threats)
    if complete is not None and verdict.screened:
        try:
            return _llm(verdict.normalized, ref, complete, timeout_s)
        except Exception as exc:  # noqa: BLE001 — any LLM failure falls back to the rules
            outcome = _rules(verdict.normalized, ref)
            outcome.errors.append(f"llm_fallback: {exc}")
            return outcome
    return _rules(verdict.normalized, ref)

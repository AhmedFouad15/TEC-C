"""Pluggable intent parsing. The rule parser always works offline; an LLM can be plugged in later as a plain
`complete(prompt) -> str` callable (the team has not chosen a provider, so no SDK is a dependency).

The LLM path is strictly guarded:
1. the firewall runs on the original text first — attacks never reach the model;
2. the model only sees the firewall-approved (normalized) text, masked by the privacy sieve;
3. its JSON is validated, tokens restored, recipients dropped, and the firewall runs again on its output;
4. any failure (timeout, provider error, bad JSON, unknown asset, refused output) falls back to the rule parser.
"""

from __future__ import annotations

import json
import queue
import re
import threading
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from tecc_brain.intent import rules
from tecc_brain.intent.firewall import scan
from tecc_brain.intent.rules import ParseOutcome
from tecc_brain.intent.sieve import mask, restore
from tecc_brain.models import ActionType, Mandate, Portfolio
from tecc_brain.reference import Reference

LLM_TIMEOUT_S = 8.0
MAX_HORIZON_DAYS = 3650
_CONSTRAINT = re.compile(r"^(?:avoid|venue):[a-z0-9_]+$")

PROMPT = """You convert a wallet owner's request into JSON. Sensitive values are replaced by tokens like <AMT_1>;
copy tokens exactly, never invent numbers or addresses. Reply with ONE JSON object and nothing else:
{{"action": one of {actions}, "asset": token symbol, "amount": number or token, "horizon_days": integer (default 365),
"constraints": list of strings like "avoid:curve" or "venue:aave"}}
Request: {request}"""


class IntentParser(Protocol):
    def parse(self, text: str, ref: Reference, portfolio: Portfolio | None = None) -> ParseOutcome: ...


class RulesParser:
    name = "rules"

    def __init__(self, known_identities: frozenset[str] = frozenset()) -> None:
        self.known_identities = known_identities

    def parse(self, text: str, ref: Reference, portfolio: Portfolio | None = None) -> ParseOutcome:
        return rules.parse(text, ref, portfolio, known_identities=self.known_identities)


class _LLMIntent(BaseModel):
    model_config = ConfigDict(extra="ignore")  # anything else the model adds (e.g. "recipients") is dropped

    action: ActionType
    asset: str
    amount: float | str
    horizon_days: int = 365
    constraints: list[str] = []


class LLMParser:
    name = "llm"

    def __init__(
        self,
        complete: Callable[[str], str],
        timeout_s: float = LLM_TIMEOUT_S,
        known_identities: frozenset[str] = frozenset(),
    ) -> None:
        self.complete = complete
        self.timeout_s = timeout_s
        self.known_identities = known_identities
        self.fallback = RulesParser(known_identities)

    def parse(self, text: str, ref: Reference, portfolio: Portfolio | None = None) -> ParseOutcome:
        verdict = scan(text, known_identities=self.known_identities)
        if not verdict.allowed:
            return self.fallback.parse(text, ref, portfolio)  # refused without ever calling the model
        if not verdict.screened:
            outcome = self.fallback.parse(text, ref, portfolio)
            outcome.errors.append("llm_skipped: text uses a script the firewall cannot screen")
            return outcome
        try:
            # The model gets exactly the string the firewall approved — never the raw input.
            mandate = self._ask_llm(verdict.normalized, text, ref, portfolio)
        except Exception as exc:  # noqa: BLE001 — every failure mode falls back to the deterministic parser
            outcome = self.fallback.parse(text, ref, portfolio)
            outcome.errors.append(f"llm_fallback: {exc}")
            return outcome
        return ParseOutcome(mandate=mandate, verdict=verdict)

    def _call_with_timeout(self, prompt: str) -> str:
        """Run the provider on a daemon thread and stop waiting after timeout_s. (A `with ThreadPoolExecutor` block
        would wait for a hung call on exit, making the timeout useless.)"""
        result: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

        def run() -> None:
            try:
                result.put((True, self.complete(prompt)))
            except Exception as exc:  # noqa: BLE001
                result.put((False, exc))

        threading.Thread(target=run, name="tecc-llm-call", daemon=True).start()
        try:
            ok, value = result.get(timeout=self.timeout_s)
        except queue.Empty as exc:
            raise RuntimeError(f"provider timed out after {self.timeout_s}s") from exc
        if not ok:
            raise value
        return str(value)

    def _ask_llm(self, approved: str, raw_text: str, ref: Reference, portfolio: Portfolio | None) -> Mandate:
        masked, vault = mask(approved)
        prompt = PROMPT.format(actions=[a.value for a in ActionType], request=masked)
        reply = self._call_with_timeout(prompt)

        match = re.search(r"\{.*\}", reply, re.DOTALL)
        if not match:
            raise ValueError("reply contained no JSON object")
        raw_json = match.group(0)
        restored = restore(raw_json, vault)
        output_verdict = scan(restored, known_identities=self.known_identities)
        if not output_verdict.allowed:
            raise ValueError(f"model output refused by firewall: {', '.join(t.value for t in output_verdict.threats)}")
        try:
            intent = _LLMIntent.model_validate(json.loads(raw_json))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"invalid model JSON: {exc.__class__.__name__}") from exc

        # Output integrity: the model may structure the request, never change it.
        amount = self._amount_from_request(intent.amount, vault)
        symbols = {s.lower(): s for s in ref.assets}
        asset = symbols.get(intent.asset.lower())
        if asset is None:
            raise ValueError(f"unknown asset {intent.asset!r}")
        mentioned = rules._find_asset(approved.lower(), ref)
        if mentioned is not None and mentioned != asset:
            raise ValueError(f"model changed the asset ({mentioned} → {asset})")
        if intent.action == ActionType.TRANSFER:
            raise ValueError(rules.TRANSFER_OUT_OF_SCOPE)
        cross_check = rules.parse(raw_text, ref, portfolio, known_identities=self.known_identities).mandate
        if cross_check is not None and (cross_check.asset, cross_check.amount) != (asset, amount):
            raise ValueError("model disagrees with the literal request")
        protocols = {v.protocol for v in ref.venues.values()}
        constraints = [c for c in intent.constraints if _CONSTRAINT.match(c) and c.split(":", 1)[1] in protocols]
        return Mandate(
            raw_text=raw_text,
            action=intent.action,
            asset=asset,
            amount=amount,
            horizon_days=min(MAX_HORIZON_DAYS, max(1, intent.horizon_days)),
            recipients=[],
            constraints=constraints,
            parser="llm",
        )

    @staticmethod
    def _amount_from_request(value: float | str, vault: dict[str, str]) -> float:
        """The amount must be one the user actually wrote: a sieve token, never a number the model made up."""
        token = str(value).strip()
        if token not in vault or not token.startswith("<AMT_"):
            raise ValueError("model gave an amount that is not in the request")
        amount = rules._find_amount(vault[token])
        if amount is None:
            raise ValueError("model gave no usable amount")
        return amount


def default_parser(
    complete: Callable[[str], str] | None = None, known_identities: frozenset[str] = frozenset()
) -> IntentParser:
    """Rule parser unless an LLM provider callable is configured."""
    if complete is not None:
        return LLMParser(complete, known_identities=known_identities)
    return RulesParser(known_identities)

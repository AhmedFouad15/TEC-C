"""Replay the AI Brain demo scenarios in demo/brain/*.json against the real API, fully offline.

    python -m scripts.brain_demo                      # all scenarios, scripted model replies, checks expectations
    python -m scripts.brain_demo ai_downgrade         # one scenario
    python -m scripts.brain_demo --live               # use the real model from TECC_BRAIN_LLM_* instead of the
                                                      # scripted replies (prints what it decided; no assertions)

Each step is one HTTP call. When a step has a `model_reply`, that reply is what the "model" returns; it is a
template resolved against the payload the Brain actually sent:
    "$REQUEST_ID"            → the payload's request_id
    "$ALL_VETOES"            → every veto id in the payload
    {"candidate": venue_id}  → the candidate_id of that venue (optionally narrowed with "label")
    "amount_usd": "$CAP"     → that candidate's max_amount_usd
    "total_auto_usd": "$AUTO_SUM" → the sum of the resolved AUTO allocations
Everything still goes through the real validator, so a fixture can also show a verdict being REFUSED.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tecc_brain.api.deps import (
    DraftCache, ProposalCache, RateLimiter, get_brain_llm, get_drafts, get_limiter, get_proposals, get_store,
)
from tecc_brain.app import app
from tecc_brain.graph.brain_llm import brain_llm_from_env
from tecc_brain.learning.store import ProfileStore

SCENARIO_DIR = Path(__file__).resolve().parents[1] / "demo" / "brain"
_MISSING = object()


def load_scenarios(names: list[str] | None = None) -> list[dict[str, Any]]:
    scenarios = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(SCENARIO_DIR.glob("*.json"))]
    if names:
        scenarios = [s for s in scenarios if s["id"] in names]
    return scenarios


def resolve_reply(template: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    reply = json.loads(json.dumps(template))
    if reply.get("request_id") == "$REQUEST_ID":
        reply["request_id"] = payload["request_id"]
    if reply.get("vetoes_honored") == "$ALL_VETOES":
        reply["vetoes_honored"] = [v["id"] for v in payload["vetoes"]]
    allocations = []
    for alloc in reply.get("allocations", []):
        if "candidate" in alloc:
            venue, label = alloc.pop("candidate"), alloc.pop("label", None)
            cand = next(c for c in payload["candidates"] if c["venue_id"] == venue and (label is None or c["label"] == label))
            alloc["candidate_id"] = cand["id"]
            if alloc.get("amount_usd") == "$CAP":
                alloc["amount_usd"] = cand["max_amount_usd"]
        allocations.append(alloc)
    reply["allocations"] = allocations
    if reply.get("total_auto_usd") == "$AUTO_SUM":
        reply["total_auto_usd"] = round(sum(a["amount_usd"] for a in allocations if a["mode"] == "AUTO"), 2)
    return reply


class ScriptedModel:
    """Stands in for the provider: returns the step's reply template, resolved against the real payload."""

    def __init__(self) -> None:
        self.template: dict[str, Any] | None = None
        self.last_payload: dict[str, Any] | None = None

    def __call__(self, system: str, payload: str) -> str:
        self.last_payload = json.loads(payload)
        assert self.template is not None
        return json.dumps(resolve_reply(self.template, self.last_payload))


def lookup(body: Any, path: str) -> Any:
    node = body
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


def check(expect: dict[str, Any], status_code: int, body: Any) -> list[str]:
    problems = []
    if "status_code" in expect and status_code != expect["status_code"]:
        problems.append(f"status_code {status_code} != {expect['status_code']}")
    for path, want in expect.get("equals", {}).items():
        got = lookup(body, path)
        same = (abs(got - want) < 0.01) if isinstance(want, float) and isinstance(got, (int, float)) else got == want
        if not same:
            problems.append(f"{path} = {got!r}, expected {want!r}")
    for path, needle in expect.get("contains", {}).items():
        got = lookup(body, path)
        if not isinstance(got, str) or needle not in got:
            problems.append(f"{path} = {got!r}, expected to contain {needle!r}")
    return problems


def run_scenario(scenario: dict[str, Any], live: bool = False, out=print) -> list[dict[str, Any]]:
    """Run every step with fresh state (profiles, drafts, limits). Returns one record per step."""
    store = ProfileStore(Path(tempfile.mkdtemp(prefix="tecc-demo-")))
    proposals, drafts = ProposalCache(), DraftCache()
    limiter = RateLimiter(by_client=False)
    model = ScriptedModel()
    live_model = brain_llm_from_env() if live else None
    current: dict[str, Any] = {"llm": None}
    app.dependency_overrides.update({
        get_store: lambda: store, get_proposals: lambda: proposals, get_drafts: lambda: drafts,
        get_limiter: lambda: limiter, get_brain_llm: lambda: current["llm"],
    })
    records = []
    try:
        client = TestClient(app)
        out(f"\n=== {scenario['title']} ===\n{scenario['story']}\n")
        for i, step in enumerate(scenario["steps"], 1):
            if step.get("model_reply") is not None:
                model.template = step["model_reply"]
                current["llm"] = live_model if live else model
            else:
                current["llm"] = None
            req = step["request"]
            r = client.request(req["method"], req["path"], json=req.get("body"))
            body = r.json()
            problems = [] if live else check(step.get("expect", {}), r.status_code, body)
            records.append({"step": step["name"], "status_code": r.status_code, "body": body, "problems": problems})
            out(f"[{i}] {step['name']}")
            out(f"    HTTP {r.status_code}" + _summary(body))
            for p in problems:
                out(f"    ✗ {p}")
            if not problems and not live:
                out("    ✓ as expected")
    finally:
        app.dependency_overrides.clear()
    return records


def _summary(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    parts = []
    if "detail" in body:
        parts.append(f"detail: {body['detail']}")
    if "status" in body:
        parts.append(f"status: {body['status']}")
    report = body.get("brain_report")
    if report:
        parts.append(f"brain: {report['decision']} by {report['producer']}")
        if report.get("fallback_reason"):
            parts.append(f"model verdict refused: {report['fallback_reason']}")
    decision = body.get("decision")
    if isinstance(decision, dict):
        parts.append(f"auto ${decision['auto_amount_usd']:,.0f}")
    text = " · ".join(parts)
    if report:
        text += f"\n    “{report['user_explanation']}”"
    return f" · {text}" if text else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenarios", nargs="*", help="scenario ids (default: all)")
    parser.add_argument("--live", action="store_true", help="use the model configured by TECC_BRAIN_LLM_*")
    args = parser.parse_args(argv)
    if args.live and brain_llm_from_env() is None:
        print("--live needs TECC_BRAIN_LLM_URL and TECC_BRAIN_LLM_KEY", file=sys.stderr)
        return 2
    failed = 0
    for scenario in load_scenarios(args.scenarios):
        records = run_scenario(scenario, live=args.live)
        failed += sum(1 for r in records if r["problems"])
    if not args.live:
        print(f"\n{'All steps behaved as expected.' if not failed else f'{failed} step(s) did not match.'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

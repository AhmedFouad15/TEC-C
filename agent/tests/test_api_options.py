"""/evaluate_options runs through the same single-pass AI Brain as /propose (D4): one decision loop, one report."""

import json

import pytest
from fastapi.testclient import TestClient

from tecc_brain.api.deps import ProposalCache, get_brain_llm, get_news_sentinel, get_proposals, get_store
from tecc_brain.app import app
from tecc_brain.graph.brain import SCHEMA_VERSION
from tecc_brain.learning.store import ProfileStore

TWO_USDC = [{"option_id": "a", "action": "deposit", "asset": "USDC", "amount_usd": 150},
            {"option_id": "b", "action": "deposit", "asset": "USDC", "amount_usd": 150}]


@pytest.fixture
def store(tmp_path):
    return ProfileStore(tmp_path)


def evaluate(store, options, llm=None, **extra):
    proposals = ProposalCache()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_proposals] = lambda: proposals
    app.dependency_overrides[get_brain_llm] = lambda: llm
    try:
        r = TestClient(app).post("/evaluate_options", json={"options": options, **extra})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200, r.text
    return r.json()


def scripted(edit):
    seen = {}

    def complete(system, payload):
        p = seen["payload"] = json.loads(payload)
        verdict = {"schema_version": SCHEMA_VERSION, "request_id": p["request_id"], "decision": "PROPOSE",
                   "allocations": [], "total_auto_usd": 0.0, "reason_codes": [],
                   "vetoes_honored": [v["id"] for v in p["vetoes"]], "signal_conflicts": ["NONE"], "confidence": 0.7,
                   "user_explanation": "Options reviewed."}
        return json.dumps(edit(verdict, p))

    complete.seen = seen
    return complete


def by_id(body):
    return {r["option_id"]: r for r in body["results"]}


# --- without a model: the rule-based baseline, now expressed as a BrainReport ----------------------


def test_split_baseline_has_a_rules_report(store):
    body = evaluate(store, TWO_USDC)
    assert body["status"] == "SPLIT"
    assert {r["allocated_usd"] for r in body["results"]} == {150}
    report = body["brain_report"]
    assert report["producer"] == "rules" and report["decision"] == "SPLIT"
    assert report["total_auto_usd"] == pytest.approx(300)
    assert len(body["intents"]) == 2


def test_all_options_invalid_is_a_reject_with_acknowledged_vetoes(store):
    body = evaluate(store, [{"option_id": "x", "action": "stake", "asset": "USDC", "amount_usd": 100, "venue_id": "lido_stake"}])
    assert body["status"] == "REJECT_ALL" and body["intents"] == []
    assert body["brain_report"]["decision"] == "REJECT"
    assert body["brain_report"]["vetoes_honored"] == ["veto:x"]


# --- with a model: the same tighten-only contract as /propose -------------------------------------------


def test_payload_describes_the_options_list(store):
    llm = scripted(lambda v, p: v)
    evaluate(store, TWO_USDC + [{"option_id": "x", "action": "stake", "asset": "USDC", "amount_usd": 100, "venue_id": "lido_stake"}], llm=llm)
    p = llm.seen["payload"]
    assert p["mandate"]["kind"] == "options_list"
    assert [o["option_id"] for o in p["mandate"]["options"]] == ["a", "b", "x"]
    assert {c["option_id"] for c in p["candidates"]} == {"a", "b"}
    assert all(c["max_amount_usd"] == pytest.approx(150) for c in p["candidates"])  # per-option AUTO caps
    assert p["vetoes"][0]["id"] == "veto:x" and p["vetoes"][0]["venue_id"] is None
    assert p["limits"]["baseline_auto_usd"] == pytest.approx(300)


def test_model_can_narrow_a_split_to_one_smaller_execution(store):
    def narrow(v, p):
        first, second = p["candidates"]
        v.update(decision="EXECUTE", total_auto_usd=100.0, reason_codes=["TOP_SCORE"], allocations=[
            {"candidate_id": first["id"], "amount_usd": 100.0, "mode": "AUTO"},
            {"candidate_id": second["id"], "amount_usd": 150.0, "mode": "PROPOSE"},
        ])
        return v

    body = evaluate(store, TWO_USDC, llm=scripted(narrow))
    assert body["brain_report"]["producer"] == "llm"
    assert body["status"] == "EXECUTE_ONE"
    modes = sorted((r["mode"], r["allocated_usd"]) for r in body["results"])
    assert modes == [("AUTO", 100.0), ("PROPOSE", 0.0)]
    assert [i["amount_usd"] for i in body["intents"]] == [100.0]


def test_model_reject_keeps_every_option_for_manual_approval(store):
    def reject(v, p):
        v.update(decision="REJECT", reason_codes=["NEGATIVE_NEWS"])
        return v

    body = evaluate(store, TWO_USDC, llm=scripted(reject))
    assert body["status"] == "REJECT_ALL" and body["intents"] == []
    assert {r["mode"] for r in body["results"]} == {"PROPOSE"}  # D3: visible, not blocked
    assert all(any("approve it yourself" in line for line in r["reasons"]) for r in body["results"])


@pytest.mark.parametrize("edit", [
    lambda v, p: {**v, "decision": "SPLIT", "total_auto_usd": 400.0, "allocations": [
        {"candidate_id": c["id"], "amount_usd": 200.0, "mode": "AUTO"} for c in p["candidates"]]},  # above each cap
    lambda v, p: {**v, "vetoes_honored": []},  # ignores the vetoed option
])
def test_invalid_verdicts_leave_the_baseline_untouched(store, edit):
    options = TWO_USDC + [{"option_id": "x", "action": "stake", "asset": "USDC", "amount_usd": 100, "venue_id": "lido_stake"}]
    baseline = evaluate(store, options)
    body = evaluate(store, options, llm=scripted(edit))
    assert body["brain_report"]["producer"] == "rules" and body["brain_report"]["fallback_reason"]
    assert body["results"] == baseline["results"] and body["status"] == baseline["status"]


# --- D8: the upgraded sentinel is Agent 1 for both entry points --------------------------------------


class SpySentinel:
    def __init__(self):
        self.calls = 0

    def _apply(self, snapshot, ref):
        self.calls += 1
        return snapshot


def test_both_entry_points_use_the_injected_news_sentinel(store):
    spy = SpySentinel()
    proposals = ProposalCache()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_proposals] = lambda: proposals
    app.dependency_overrides[get_news_sentinel] = lambda: spy
    try:
        client = TestClient(app)
        assert client.post("/api/mandate/propose", json={"text": "Optimize my $1,500 USDC"}).status_code == 200
        assert client.post("/evaluate_options", json={"options": TWO_USDC}).status_code == 200
    finally:
        app.dependency_overrides.clear()
    assert spy.calls == 2

"""The demo fixtures in demo/brain/ must keep matching the real API (they are the team's simulation scripts)."""

import json

import pytest
from fastapi.testclient import TestClient

from scripts.brain_demo import load_scenarios, resolve_reply, run_scenario
from tecc_brain.api.deps import ProposalCache, get_brain_llm, get_proposals, get_store
from tecc_brain.app import app
from tecc_brain.learning.store import ProfileStore


@pytest.mark.parametrize("scenario", load_scenarios(), ids=lambda s: s["id"])
def test_demo_scenario_behaves_as_scripted(scenario):
    records = run_scenario(scenario, out=lambda *_: None)
    assert records and all(not r["problems"] for r in records), [(r["step"], r["problems"]) for r in records if r["problems"]]


def test_both_demo_moments_exist():
    assert {s["id"] for s in load_scenarios()} >= {"ai_downgrade", "injection_refusal"}


def test_template_placeholders_resolve():
    payload = {"request_id": "r1", "vetoes": [{"id": "veto:x"}],
               "candidates": [{"id": "c0", "venue_id": "aave_v3_usdc", "label": "BEST", "max_amount_usd": 400.0}]}
    reply = resolve_reply({"request_id": "$REQUEST_ID", "vetoes_honored": "$ALL_VETOES", "total_auto_usd": "$AUTO_SUM",
                           "allocations": [{"candidate": "aave_v3_usdc", "amount_usd": "$CAP", "mode": "AUTO"}]}, payload)
    assert reply == {"request_id": "r1", "vetoes_honored": ["veto:x"], "total_auto_usd": 400.0,
                     "allocations": [{"candidate_id": "c0", "amount_usd": 400.0, "mode": "AUTO"}]}


def test_a_breaking_headline_reaches_the_model_as_quoted_evidence(tmp_path):
    """Regression: market-wide sentinel summaries must not crowd the order's own headline out of the payload."""
    seen = {}

    def spy(system, payload):
        seen["p"] = json.loads(payload)
        return "{}"

    store, proposals = ProfileStore(tmp_path), ProposalCache()
    app.dependency_overrides.update({get_store: lambda: store, get_proposals: lambda: proposals, get_brain_llm: lambda: spy})
    headline = "USDC liquidity thins on Curve as market makers pull back; analysts warn of wider spreads"
    try:
        TestClient(app).post("/api/mandate/propose", json={"text": "Optimize my $1,500 USDC", "headline": headline})
    finally:
        app.dependency_overrides.clear()
    assert headline in seen["p"]["untrusted_text"].values()
    assert all(n["evidence_id"] in seen["p"]["untrusted_text"] for n in seen["p"]["news"])

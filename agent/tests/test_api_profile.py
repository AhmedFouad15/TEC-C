import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tecc_brain.api.deps import ProposalCache, get_proposals, get_store
from tecc_brain.app import app
from tecc_brain.learning.onboarding import QUIZ
from tecc_brain.learning.store import ProfileStore

ACCOUNT = "0x" + "ab" * 20


@pytest.fixture
def store(tmp_path):
    return ProfileStore(tmp_path)


@pytest.fixture
def client(store):
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_proposals] = ProposalCache
    yield TestClient(app)
    app.dependency_overrides.clear()


def answers(points):
    return {q.id: next(o.id for o in q.options if o.points == p) for q, p in zip(QUIZ, points)}


def ratify(n, venue="aave_v3_usdc", usd=100, at="2026-10-16T09:00:00Z"):
    return {"event_id": f"r{n}", "signal": "ratify", "venue_id": venue, "amount_usd": usd, "at": at}


# --- profile & onboarding -----------------------------------------------------------------------


def test_demo_profile_view(client):
    body = client.get("/api/profile/demo").json()
    assert body["tier"] == 2 and body["lam"] == 1.0 and body["tau"] == 0.6
    assert body["lam_band"] == [0.5, 2.0]
    assert body["soft_limit_usd"] == pytest.approx(400)
    aave = next(a for a in body["approvals"] if a["venue_id"] == "aave_v3_usdc")
    assert aave["approval"] == pytest.approx(5 / 7)


def test_quiz_is_served_for_the_frontend(client):
    quiz = client.get("/api/profile/quiz").json()
    assert len(quiz) == 5 and all(len(q["options"]) == 3 for q in quiz)


def test_onboarding_creates_a_profile_once(client):
    r = client.post("/api/profile/onboard", json={"account": ACCOUNT, "answers": answers([2, 2, 2, 2, 2])})
    assert r.status_code == 200
    assert r.json()["profile"]["tier"] == 3
    again = client.post("/api/profile/onboard", json={"account": ACCOUNT, "answers": answers([0, 0, 0, 0, 0])})
    assert again.status_code == 409
    reset = client.post("/api/profile/onboard", json={"account": ACCOUNT, "answers": answers([0] * 5), "reset": True})
    assert reset.json()["profile"]["tier"] == 1


def test_bad_quiz_answers_are_422(client):
    r = client.post("/api/profile/onboard", json={"account": ACCOUNT, "answers": {"horizon": "soon"}})
    assert r.status_code == 422


# --- review sync --------------------------------------------------------------------------------


def test_review_sync_learns_and_persists(client, store):
    r = client.post("/api/review/sync", json={"account": "demo", "events": [ratify(1)]})
    body = r.json()
    assert body["applied"] == 1 and body["duplicates"] == 0
    assert store.load("demo").tau == pytest.approx(0.62)
    assert body["results"][0]["changes"]


def test_review_sync_is_idempotent(client):
    client.post("/api/review/sync", json={"account": "demo", "events": [ratify(1)]})
    body = client.post("/api/review/sync", json={"account": "demo", "events": [ratify(1)]}).json()
    assert body["applied"] == 0 and body["duplicates"] == 1


def test_notes_through_sync_become_preferences(client):
    note = {"event_id": "n1", "signal": "note", "venue_id": "curve_steth_eth", "amount_usd": 0,
            "at": "2026-10-16T09:00:00Z", "note": "stop using Curve, I hate IL"}
    client.post("/api/review/sync", json={"account": "demo", "events": [note]})
    body = client.get("/api/profile/demo").json()
    assert "curve" in body["dislikes"]
    assert body["cost_factors"]["c_out_stress"] == pytest.approx(1.1)


def test_naive_event_times_are_rejected(client):
    bad = {**ratify(1), "at": "2026-10-16T09:00:00"}
    assert client.post("/api/review/sync", json={"account": "demo", "events": [bad]}).status_code == 422


# --- levers -------------------------------------------------------------------------------------


def test_levers_endpoint_advises_heartbeat_and_shrink(client):
    body = client.post(f"/api/levers/demo", json={"radius_usd": 500, "elasticity_enabled": True,
                                                  "held_cluster_stressed": True}).json()
    kinds = [a["kind"] for a in body["actions"]]
    assert "heartbeat" in kinds and "shrink" in kinds


# --- backtest -----------------------------------------------------------------------------------


def test_backtests_are_listed_and_replayed(client):
    episodes = client.get("/api/backtest").json()
    assert "usdc_svb_2023" in episodes
    body = client.post("/api/backtest/ust_2022").json()
    assert body["strategies"]["tec_c"]["pnl_pct"] > body["strategies"]["mean_reversion"]["pnl_pct"]
    assert client.post("/api/backtest/nope").status_code == 404


# --- sentinel -----------------------------------------------------------------------------------


def test_headline_endpoint_shows_before_and_after(client):
    body = client.post("/api/sentinel/headline", json={
        "headline": "Circle says $3.3bn of USDC reserves are stuck at failed Silicon Valley Bank"}).json()
    assert body["signal"]["symbol"] == "USDC"
    assert body["after"]["p_distress"] > body["before"]["p_distress"]
    assert body["source"].startswith("offline lexicon")


def test_propose_accepts_a_headline_for_scene_2(client):
    body = client.post("/api/mandate/propose", json={
        "text": "Optimize my $1,500 USDC",
        "headline": "Circle says $3.3bn of USDC reserves are stuck at failed Silicon Valley Bank"}).json()
    sentinel = next(a for a in body["agents"] if a["agent"] == "nlp_sentinel")
    assert any("Silicon Valley" in line for line in sentinel["lines"])


# --- spec ---------------------------------------------------------------------------------------


def test_exported_spec_lists_every_api_path(tmp_path):
    from scripts.export_api_spec import export

    out = export(tmp_path / "api_spec.json")
    paths = set(json.loads(Path(out).read_text())["paths"])
    for p in ("/api/mandate/parse", "/api/mandate/propose", "/api/mandate/execute", "/api/risk/regimes",
              "/api/profile/{account}", "/api/profile/onboard", "/api/review/sync", "/api/backtest/{episode}",
              "/api/sentinel/headline", "/api/levers/{account}"):
        assert p in paths, p

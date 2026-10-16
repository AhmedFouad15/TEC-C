import pytest
from fastapi.testclient import TestClient

from tecc_brain.api.deps import ProposalCache, get_proposals, get_store
from tecc_brain.app import app
from tecc_brain.learning.store import ProfileStore


@pytest.fixture(autouse=True)
def isolated(tmp_path):
    cache = ProposalCache()
    app.dependency_overrides[get_store] = lambda: ProfileStore(tmp_path)
    app.dependency_overrides[get_proposals] = lambda: cache
    yield
    app.dependency_overrides.clear()


def test_other_machines_are_refused_without_a_token(monkeypatch):
    monkeypatch.delenv("TECC_API_TOKEN", raising=False)
    remote = TestClient(app, client=("10.0.0.5", 50000))
    assert remote.get("/api/profile/demo").status_code == 403
    assert remote.get("/health").status_code == 200  # liveness stays public


def test_token_is_required_when_configured(monkeypatch):
    monkeypatch.setenv("TECC_API_TOKEN", "s3cret")
    client = TestClient(app)
    assert client.get("/api/profile/demo").status_code == 401
    assert client.get("/api/profile/demo", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/profile/demo", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    remote = TestClient(app, client=("10.0.0.5", 50000))
    assert remote.get("/api/profile/demo", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_a_proposal_can_only_be_executed_for_its_own_account(monkeypatch):
    monkeypatch.delenv("TECC_API_TOKEN", raising=False)
    client = TestClient(app)
    pid = client.post("/api/mandate/propose", json={"text": "Deposit 300 USDC into Aave"}).json()["proposal_id"]
    other = "0x" + "cd" * 20
    r = client.post("/api/mandate/execute", json={"proposal_id": pid, "label": "BEST", "account": other})
    assert r.status_code == 404
    ok = client.post("/api/mandate/execute", json={"proposal_id": pid, "label": "BEST", "account": "demo"})
    assert ok.status_code == 200  # the failed attempt did not burn the proposal

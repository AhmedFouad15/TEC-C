"""Pre-flight GO fixes (Phase 2 audit): retryable FaceID breakout, real vault state, atomic tether, served web UI."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

import tecc_brain.api.vault as vault_api
from tecc_brain.api.deps import ProposalCache, get_proposals, get_store
from tecc_brain.app import app
from tecc_brain.models import ActionType, CardLabel, ExecutionIntent, VaultState, usd_to_onchain
from tecc_brain.onchain.executor import MarketRouter


class MemStore:
    def __init__(self):
        self.d = {}

    def load(self, account):
        return self.d.get(account.lower())

    def save(self, profile):
        self.d[profile.account.lower()] = profile


@pytest.fixture
def api():
    store, proposals = MemStore(), ProposalCache()
    app.dependency_overrides.update({get_store: lambda: store, get_proposals: lambda: proposals})
    yield TestClient(app)
    app.dependency_overrides.pop(get_store, None)
    app.dependency_overrides.pop(get_proposals, None)


def _big_order(api):
    body = api.post("/api/mandate/propose", json={"text": "deposit 4821 dollars of USDC"}).json()
    card = body["decision"]["cards"][0]
    return body["proposal_id"], {"proposal_id": body["proposal_id"], "label": card["label"],
                                 "venue_id": card["candidate"]["venue_id"]}


# --- FaceID breakout: a step, not a burn ----------------------------------------------------------------------


def test_breakout_keeps_the_proposal_for_a_retry(api):
    _, req = _big_order(api)
    first = api.post("/api/mandate/execute", json=req)
    second = api.post("/api/mandate/execute", json=req)
    assert first.status_code == 200 and first.json()["intent"]["status"] == "breakout_required"
    assert "passkey" in first.json()["message"]
    assert second.status_code == 200 and second.json()["intent"]["status"] == "breakout_required"  # not 409


def test_a_verified_passkey_completes_the_breakout(api, monkeypatch, _simulated_markets_only):
    import tecc_brain.api.biometrics as biometrics

    class Verified:
        def is_biometric_window_active(self, account, now=None):
            return True, None

    monkeypatch.setattr(biometrics, "get_biometric_manager", lambda: Verified())
    _, req = _big_order(api)
    out = api.post("/api/mandate/execute", json=req).json()
    assert out["intent"]["status"] == "simulated"  # routed past today's radius with the passkey window
    assert out["intent"]["amount_usd"] == pytest.approx(4821 - 400)
    again = api.post("/api/mandate/execute", json=req)
    assert again.status_code == 409  # executed once, then the proposal is spent


# --- the real vault state sizes the automatic slice -----------------------------------------------------------


def test_live_vault_state_sizes_the_automatic_slice(api, monkeypatch):
    monkeypatch.setattr(vault_api, "live_vault_state",
                        lambda account: VaultState(tether_radius_usd=500, spent_today_usd=300) if account == "demo" else None)
    out = api.post("/api/mandate/propose", json={"text": "deposit 300 dollars of USDC"}).json()
    assert out["intent"]["amount_usd"] == pytest.approx((0.5 + 0.5 * 0.6) * 200)  # soft tether of the $200 left
    sent = api.post("/api/mandate/propose", json={"text": "deposit 300 dollars of USDC",
                                                  "vault": {"tether_radius_usd": 500, "spent_today_usd": 0}}).json()
    assert sent["intent"]["amount_usd"] == pytest.approx(300)  # an explicit vault in the request wins


def test_no_live_vault_falls_back_to_the_request(monkeypatch):
    monkeypatch.setattr(vault_api, "load_market", lambda network: None)
    assert vault_api.live_vault_state("demo") is None
    assert vault_api.live_vault_state("someone-else") is None


# --- S4: check → submit → record is atomic ----------------------------------------------------------------------


def test_concurrent_live_orders_cannot_both_pass_the_remaining_allowance():
    class SlowLive:
        def submit(self, intent, account):
            time.sleep(0.2)
            return intent.model_copy(update={"status": "submitted", "tx_hash": "0x" + "1" * 64})

    router = MarketRouter(crypto=SlowLive(), daily_limit_usd=500)
    intent = ExecutionIntent(card_label=CardLabel.BEST, venue_id="aave_v3_usdc", action=ActionType.DEPOSIT,
                             asset_in="USDC", amount_usd=400, amount_onchain=usd_to_onchain(400))
    results = []
    threads = [threading.Thread(target=lambda: results.append(router.submit(intent, "demo").status)) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ["failed", "submitted"]
    assert router.tether_tracker.get_spent("demo") == pytest.approx(400)


# --- S5: one scan at a time ------------------------------------------------------------------------------------------


def test_overlapping_scans_run_one_after_the_other(_simulated_markets_only):
    from tecc_brain.pegguard import PegGuardAutonomousScanner

    scanner = PegGuardAutonomousScanner(router=_simulated_markets_only, store=MemStore())
    scanner.set_enabled("demo", True)
    inside = []
    original = scanner._scan_tick

    def tracked(*args, **kwargs):
        inside.append(1)
        assert len(inside) == 1, "two scans ran at the same time"
        try:
            time.sleep(0.05)
            return original(*args, **kwargs)
        finally:
            inside.pop()

    scanner._scan_tick = tracked
    reports = []
    threads = [threading.Thread(target=lambda: reports.append(scanner.scan_tick(
        "demo", symbols=["USDC"], price_overrides={"USDC": 0.97}, vault=VaultState(tether_radius_usd=500))))
        for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(reports) == 2


# --- S8: the web UI from the API port -----------------------------------------------------------------------------


def test_the_web_ui_is_served_from_the_api_port():
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/app.html").status_code == 200
    assert client.get("/assets/js/app.js").status_code == 200
    assert client.get("/health").json()["status"] == "ok"  # API routes still win over the static mount
    assert "x_search" in client.get("/api/settings").json()


def test_the_ui_served_by_the_api_is_same_origin_but_other_sites_stay_refused(monkeypatch):
    monkeypatch.delenv("TECC_API_TOKEN", raising=False)
    client = TestClient(app, base_url="http://127.0.0.1:8000")
    own = client.get("/api/settings", headers={"Origin": "http://127.0.0.1:8000"})
    assert own.status_code == 200
    other = client.get("/api/settings", headers={"Origin": "http://evil.example"})
    assert other.status_code == 403
    sneaky = client.get("/api/settings", headers={"Origin": "http://127.0.0.1:9999"})
    assert sneaky.status_code == 403

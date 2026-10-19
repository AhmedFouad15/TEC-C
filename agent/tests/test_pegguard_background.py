"""Tests for autonomous 24/7 PegGuard background arbitrage runner & telemetry."""

import time
from tecc_brain.pegguard import PegGuardAutonomousScanner
from tecc_brain.learning.store import ProfileStore
from tecc_brain.learning.update import new_profile
from tecc_brain.models import RiskTier
from starlette.testclient import TestClient
from tecc_brain.app import app


def test_scanner_background_worker_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("TECC_STATE_DIR", str(tmp_path))
    store = ProfileStore(root=tmp_path / "profiles")
    profile = new_profile("test_acct", RiskTier.BALANCED)
    store.save(profile)

    scanner = PegGuardAutonomousScanner(store=store)

    class FastMockLiveFeed:
        def get_live_peg_ratios(self):
            return {"USDC": 1.0, "USDT": 1.0, "DAI": 1.0}

    scanner._live_data_source = FastMockLiveFeed()

    # 1. Initially disabled, no background worker running
    assert not scanner.is_enabled("test_acct")
    init_scan = scanner.get_last_scan("test_acct")
    assert init_scan["status"] == "idle"

    # 2. Enable: start_background_scanner runs with rapid interval (0.05s)
    scanner.set_enabled("test_acct", True)
    assert scanner.is_enabled("test_acct")
    scanner.stop_background_scanner("test_acct")
    scanner.start_background_scanner("test_acct", interval_seconds=0.05)

    # Allow worker to run at least 1 tick
    time.sleep(0.15)

    telemetry = scanner.get_last_scan("test_acct")
    assert telemetry["scanned_count"] == 25
    assert telemetry["timestamp"] is not None
    assert telemetry["timestamp_unix"] is not None
    assert telemetry["seconds_ago"] >= 0.0
    assert telemetry["status"] == "scanned"

    # 3. Disable -> worker stops cleanly
    scanner.set_enabled("test_acct", False)
    assert not scanner.is_enabled("test_acct")
    assert "test_acct" not in scanner._background_threads

    # 4. Profile persistence verification
    saved_prof = store.load("test_acct")
    assert saved_prof.arbitrage_enabled is False


def test_arbitrage_api_endpoints_return_last_scan():
    client = TestClient(app, base_url="http://127.0.0.1:8000")

    # Status endpoint
    res = client.get("/api/arbitrage/status?account=demo")
    assert res.status_code == 200
    data = res.json()
    assert "last_scan" in data
    assert data["monitored_assets_count"] == 25

    # Toggle endpoint
    res_toggle = client.post("/api/arbitrage/toggle", json={"account": "demo", "enabled": True})
    assert res_toggle.status_code == 200
    data_toggle = res_toggle.json()
    assert data_toggle["enabled"] is True
    assert "last_scan" in data_toggle

    # Toggle back to False
    res_off = client.post("/api/arbitrage/toggle", json={"account": "demo", "enabled": False})
    assert res_off.status_code == 200
    assert res_off.json()["enabled"] is False

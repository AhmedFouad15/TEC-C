"""Finding E (scheduler never ran) and H (monitor wrote to the real profile store; comment ids collided)."""

import pytest
from fastapi.testclient import TestClient

from tecc_brain.api.deps import ProposalCache, get_proposals, get_store
from tecc_brain.app import app
from tecc_brain.learning.store import ProfileStore
from tecc_brain.monitor import hourly


def test_hourly_job_is_scheduled_not_paused(monkeypatch):
    pytest.importorskip("apscheduler")
    monkeypatch.setenv("TECC_ENABLE_HOURLY_MONITOR", "1")
    monkeypatch.setenv("TECC_MONITOR_INTERVAL_MINUTES", "60")
    hourly.stop_scheduler()
    try:
        hourly.start_scheduler()
        job = hourly._scheduler.get_job("tecc_hourly_monitor")
        assert job is not None
        assert job.next_run_time is not None  # paused jobs have next_run_time None and never fire
    finally:
        hourly.stop_scheduler()


def test_scheduler_stays_off_unless_enabled(monkeypatch):
    monkeypatch.delenv("TECC_ENABLE_HOURLY_MONITOR", raising=False)
    hourly.stop_scheduler()
    hourly.start_scheduler()
    assert hourly._scheduler is None


@pytest.fixture
def client(tmp_path):
    store = ProfileStore(tmp_path)
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_proposals] = ProposalCache
    yield TestClient(app), store, tmp_path
    app.dependency_overrides.clear()


def test_manual_trigger_uses_the_api_store(client, monkeypatch):
    c, store, tmp = client
    seen = []
    real = hourly.run_once

    def spy(*args, **kwargs):
        seen.append(kwargs.get("store"))
        return real(*args, **kwargs)

    monkeypatch.setattr(hourly, "run_once", spy)
    assert c.post("/trigger_hourly_monitor", json={"scenario": "usdc_distress"}).status_code == 200
    assert seen and seen[0] is store


def test_two_comments_in_the_same_second_are_both_learned(client):
    c, store, _ = client
    body = {"options": [{"option_id": "a", "action": "deposit", "asset": "USDC", "amount_usd": 100}]}
    c.post("/evaluate_options", json={**body, "comment": "stop using Curve"})
    c.post("/evaluate_options", json={**body, "comment": "Lido is great"})
    history = store.load("demo").history
    assert len([e for e in history if e.event_id.startswith("options-comment:")]) == 2


# --- H: shared configs agree with the code ------------------------------------------------------------

import json  # noqa: E402
import re  # noqa: E402
from pathlib import Path  # noqa: E402

from tecc_brain.onchain.mandate import DOMAIN_NAME  # noqa: E402

SHARED = Path(__file__).resolve().parents[2] / "shared"


def _addresses(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _addresses(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _addresses(v)
    elif isinstance(obj, str) and obj.startswith("0x") and len(obj) <= 44 and re.fullmatch(r"0x[0-9a-fA-F]+", obj):
        yield obj


def test_shared_configs_use_the_eip712_name_the_brain_signs_with():
    for path in SHARED.glob("contracts*.json"):
        domain = json.loads(path.read_text()).get("eip712", {}).get("domain")
        if domain:
            assert domain["name"] == DOMAIN_NAME, path.name


def test_placeholder_addresses_are_valid_20_byte_addresses():
    for path in SHARED.glob("contracts.*.json"):
        for addr in _addresses(json.loads(path.read_text())):
            assert len(addr) == 42, f"{path.name}: {addr}"

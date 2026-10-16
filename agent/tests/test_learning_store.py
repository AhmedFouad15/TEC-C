from datetime import datetime, timezone

import pytest

from tecc_brain.learning.store import ProfileStore
from tecc_brain.learning.update import FeedbackEvent, Signal, learn, new_profile
from tecc_brain.models import RiskTier

ACCOUNT = "0x" + "ab" * 20


def test_round_trip_preserves_everything(tmp_path):
    store = ProfileStore(tmp_path)
    profile = new_profile(ACCOUNT, RiskTier.BALANCED)
    profile = learn(profile, FeedbackEvent(event_id="1", signal=Signal.RATIFY, venue_id="aave_v3_usdc", amount_usd=500,
                                           at=datetime(2026, 10, 16, tzinfo=timezone.utc))).profile
    store.save(profile)
    assert store.load(ACCOUNT) == profile


def test_missing_account_loads_none_and_get_or_create_makes_one(tmp_path):
    store = ProfileStore(tmp_path)
    assert store.load(ACCOUNT) is None
    created = store.get_or_create(ACCOUNT, RiskTier.CONSERVATIVE)
    assert created.lam == 3.0
    assert store.load(ACCOUNT) == created
    assert store.get_or_create(ACCOUNT, RiskTier.AGGRESSIVE).tier == RiskTier.CONSERVATIVE  # existing wins


@pytest.mark.parametrize("bad", ["../etc/passwd", "a/b", "", "x" * 65, "..", "0xZZ", "name with space"])
def test_account_names_cannot_escape_the_store(tmp_path, bad):
    store = ProfileStore(tmp_path)
    with pytest.raises(ValueError):
        store.load(bad)


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(new_profile("demo", RiskTier.BALANCED))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["demo.json"]


def test_addresses_are_case_insensitive(tmp_path):
    store = ProfileStore(tmp_path)
    store.save(new_profile(ACCOUNT, RiskTier.BALANCED))
    assert store.load(ACCOUNT.upper().replace("0X", "0x")) is not None


def test_default_root_comes_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TECC_STATE_DIR", str(tmp_path))
    assert ProfileStore().root == tmp_path / "profiles"

import pytest

from tecc_brain.market import MarketDataSource, SnapshotSource
from tecc_brain.reference import load_reference

DEMO_APYS = {
    "lido_stake": 0.0310,
    "curve_steth_eth": 0.0685,
    "aave_v3_usdc": 0.0420,
    "shibor_mmf": 0.0215,
    "paxg_hold": 0.0180,
}


def test_bundled_snapshots_are_listed():
    assert {"demo", "usdc_distress"} <= set(SnapshotSource.available())


def test_snapshot_source_satisfies_the_interface():
    assert isinstance(SnapshotSource("demo"), MarketDataSource)


def test_unknown_snapshot_is_rejected():
    with pytest.raises(ValueError):
        SnapshotSource("nope")


@pytest.mark.parametrize("name", ["demo", "usdc_distress"])
def test_snapshot_venues_and_pegs_are_known(name):
    snapshot = SnapshotSource(name).snapshot()
    ref = load_reference()
    assert set(snapshot.venues) <= set(ref.venues)
    assert set(snapshot.pegs) <= set(ref.assets)
    assert snapshot.hurdle_rate == snapshot.shibor["1Y"]


def test_demo_snapshot_has_the_pitch_apys():
    venues = SnapshotSource("demo").snapshot().venues
    assert {vid: venues[vid].apy for vid in DEMO_APYS} == DEMO_APYS


def test_distress_snapshot_replays_svb_usdc():
    peg = SnapshotSource("usdc_distress").snapshot().pegs["USDC"]
    assert (peg.price, peg.coverage, peg.redemption_status) == (0.88, 0.9175, 0.5)

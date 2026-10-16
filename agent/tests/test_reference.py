"""Integrity of the static tables — the risk engine's numbers are only as good as this data."""

import pytest

from tecc_brain.reference import load_reference

REF = load_reference()


def test_venue_assets_exist():
    for venue in REF.venues.values():
        symbols = [*venue.accepts, *venue.exposures] + ([venue.produces] if venue.produces else [])
        for symbol in symbols:
            assert symbol in REF.assets, f"{venue.id} references unknown asset {symbol}"


def test_contagion_links_reference_known_assets():
    for link in REF.contagion:
        assert link.source in REF.assets and link.target in REF.assets


def test_contagion_links_stay_inside_a_cluster():
    for link in REF.contagion:
        assert REF.assets[link.source].cluster == REF.assets[link.target].cluster


def test_pegged_assets_have_a_cluster():
    for asset in REF.assets.values():
        if asset.peg is not None:
            assert asset.cluster, f"{asset.symbol} is pegged but has no contagion cluster"


def test_every_entry_explains_itself():
    entries = [*REF.assets.values(), *REF.venues.values(), *REF.contagion]
    for entry in entries:
        assert entry.note.strip(), f"missing rationale note on {entry}"
    for episode in REF.episodes:
        assert episode["note"].strip()


@pytest.mark.parametrize("episode", REF.episodes, ids=lambda e: e["id"])
def test_episode_expected_probabilities_sum_to_one(episode):
    expected = episode["expected"]
    total = expected["p_normal"] + expected["p_distress"] + expected["p_failure"]
    assert total == pytest.approx(1.0, abs=0.002)


@pytest.mark.parametrize("episode", REF.episodes, ids=lambda e: e["id"])
def test_episode_assets_are_known_pegged_assets(episode):
    assert REF.assets[episode["asset"]].peg is not None

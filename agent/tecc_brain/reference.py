"""Static reference data: assets, venues, contagion links and historical episodes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any

from tecc_brain.models import Asset, ContagionLink, Venue


def read_data_json(filename: str) -> Any:
    """Read a JSON file bundled in tecc_brain/data (works from any CWD and when installed)."""
    return json.loads(resources.files("tecc_brain.data").joinpath(filename).read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Reference:
    assets: dict[str, Asset]
    venues: dict[str, Venue]
    contagion: list[ContagionLink]
    episodes: list[dict[str, Any]]

    def episode(self, episode_id: str) -> dict[str, Any]:
        for episode in self.episodes:
            if episode["id"] == episode_id:
                return episode
        raise KeyError(episode_id)


@lru_cache(maxsize=1)
def load_reference() -> Reference:
    assets = [Asset.model_validate(row) for row in read_data_json("assets.json")]
    venues = [Venue.model_validate(row) for row in read_data_json("venues.json")]
    return Reference(
        assets={a.symbol: a for a in assets},
        venues={v.id: v for v in venues},
        contagion=[ContagionLink.model_validate(row) for row in read_data_json("contagion.json")],
        episodes=read_data_json("episodes.json"),
    )

"""Offline market snapshots bundled with the package — the demo never depends on the internet."""

from __future__ import annotations

from importlib import resources

from tecc_brain.models import MarketSnapshot
from tecc_brain.reference import read_data_json

_PREFIX = "snapshot_"


class SnapshotSource:
    """Serves a bundled snapshot file, e.g. SnapshotSource("demo") -> data/snapshot_demo.json."""

    def __init__(self, snapshot_name: str = "demo") -> None:
        if snapshot_name not in self.available():
            raise ValueError(f"Unknown snapshot {snapshot_name!r}; available: {self.available()}")
        self.snapshot_name = snapshot_name
        self.name = f"snapshot:{snapshot_name}"

    @staticmethod
    def available() -> list[str]:
        files = resources.files("tecc_brain.data").iterdir()
        return sorted(f.name[len(_PREFIX) : -len(".json")] for f in files if f.name.startswith(_PREFIX))

    def snapshot(self) -> MarketSnapshot:
        return MarketSnapshot.model_validate(read_data_json(f"{_PREFIX}{self.snapshot_name}.json"))

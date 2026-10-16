"""Market data source interface. Live, Member 4 and snapshot sources all implement it (Phase 8 chains them)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from tecc_brain.models import MarketSnapshot


@runtime_checkable
class MarketDataSource(Protocol):
    name: str

    def snapshot(self) -> MarketSnapshot:
        """Return the latest market view. Must not raise for transient issues if a fallback exists."""
        ...

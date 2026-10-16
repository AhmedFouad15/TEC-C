"""Shared API dependencies (overridable in tests) and request models used by several routers."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field

from tecc_brain.graph.pipeline import PipelineResult
from tecc_brain.learning.store import ProfileStore, account_key
from tecc_brain.models import VaultState
from tecc_brain.reference import Reference, load_reference

Scenario = Literal["demo", "usdc_distress"]  # bundled market snapshots (live data arrives in Phase 8)


def _valid_account(account: str) -> str:
    account_key(account)  # raises ValueError → 422 for path tricks or malformed addresses
    return account


Account = Annotated[str, AfterValidator(_valid_account)]

PROPOSAL_TTL_S = 3600
MAX_PROPOSALS = 500


class VaultIn(BaseModel):
    """What the UI knows about the vault today (Phase 7 reads it from TetherGuardHook instead)."""

    tether_radius_usd: float = Field(500.0, ge=0, le=1e9)
    spent_today_usd: float = Field(0.0, ge=0, le=1e9)
    heartbeat_alive: bool = True

    def to_state(self) -> VaultState:
        return VaultState(**self.model_dump())


@dataclass
class Proposal:
    id: str
    account: str
    result: PipelineResult
    vault: VaultState
    created: float
    executed: bool = False


class ProposalCache:
    """In-memory proposals so /execute can refer to what /propose showed. Bounded and expiring."""

    def __init__(self, ttl_s: float = PROPOSAL_TTL_S, max_items: int = MAX_PROPOSALS) -> None:
        self.ttl_s, self.max_items = ttl_s, max_items
        self._items: dict[str, Proposal] = {}
        self._lock = threading.Lock()

    def add(self, account: str, result: PipelineResult, vault: VaultState) -> str:
        with self._lock:
            self._evict()
            pid = uuid.uuid4().hex
            self._items[pid] = Proposal(pid, account, result, vault, time.monotonic())
            return pid

    def get(self, pid: str) -> Proposal | None:
        with self._lock:
            self._evict()
            return self._items.get(pid)

    def claim(self, pid: str) -> tuple[Proposal | None, bool]:
        """(proposal, first_time): atomically marks it executed so two clicks can't both execute."""
        with self._lock:
            self._evict()
            item = self._items.get(pid)
            if item is None:
                return None, False
            first = not item.executed
            item.executed = True
            return item, first

    def release(self, pid: str) -> None:
        with self._lock:
            if pid in self._items:
                self._items[pid].executed = False

    def _evict(self) -> None:
        now = time.monotonic()
        for pid in [p for p, item in self._items.items() if now - item.created > self.ttl_s]:
            del self._items[pid]
        while len(self._items) >= self.max_items:
            del self._items[next(iter(self._items))]


@lru_cache(maxsize=1)
def _store() -> ProfileStore:
    return ProfileStore()


@lru_cache(maxsize=1)
def _proposals() -> ProposalCache:
    return ProposalCache()


def get_store() -> ProfileStore:
    return _store()


def get_proposals() -> ProposalCache:
    return _proposals()


@lru_cache(maxsize=1)
def get_ref() -> Reference:
    return load_reference()

"""Shared API dependencies (overridable in tests) and request models used by several routers."""

from __future__ import annotations

import hashlib
import hmac
import os
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Annotated, Any, Literal

from fastapi import HTTPException, Request
from pydantic import AfterValidator, BaseModel, Field

from tecc_brain.graph.brain import BrainLLM
from tecc_brain.graph.brain_llm import brain_llm_from_env
from tecc_brain.graph.pipeline import PipelineResult
from tecc_brain.intent.rules import ParseOutcome
from tecc_brain.learning.store import ProfileStore, account_key
from tecc_brain.models import ExecutionIntent, Mandate, VaultState
from tecc_brain.onchain.anchoring import AuditAnchorService
from tecc_brain.onchain.executor import MarketRouter
from tecc_brain.reference import Reference, load_reference
from tecc_brain.sentinel.blended import NewsRiskSentinel

Scenario = Literal["demo", "usdc_distress", "live"]  # bundled market snapshots or live Chainlink/DeFiLlama feed


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
    auto_executed_usd: dict[str, float] = field(default_factory=dict)  # card key → USD that already ran automatically


def card_key(card) -> str:
    """Identifies one card inside a proposal: the option it answers (options flow) or its venue."""
    return card.option_id or card.candidate.venue_id


class ProposalCache:
    """In-memory proposals so /execute can refer to what /propose showed. Bounded and expiring."""

    def __init__(self, ttl_s: float = PROPOSAL_TTL_S, max_items: int = MAX_PROPOSALS) -> None:
        self.ttl_s, self.max_items = ttl_s, max_items
        self._items: dict[str, Proposal] = {}
        self._lock = threading.Lock()

    def add(self, account: str, result: PipelineResult, vault: VaultState,
            auto_executed_usd: dict[str, float] | None = None) -> str:
        with self._lock:
            self._evict()
            pid = uuid.uuid4().hex
            self._items[pid] = Proposal(pid, account, result, vault, time.monotonic(),
                                        auto_executed_usd=dict(auto_executed_usd or {}))
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


DRAFT_TTL_S = 900  # 15 min: an input-stage artifact, lives much shorter than a confirmed Proposal
MAX_DRAFTS = 500
MAX_REVISIONS = 5  # revise 5x, then the UI should steer the user to /evaluate_options (no free text at all)
MAX_OPEN_DRAFTS_PER_ACCOUNT = 3  # stops "start a new draft" from side-stepping the revision cap


def draft_version(mandate: Mandate | None, revision: int) -> str:
    """Content hash of exactly what the user is shown. /confirm must echo it back, so a revision made in another
    tab (or by anyone else holding the draft_id) after the user looked can never be confirmed by mistake."""
    body = mandate.model_dump_json(exclude={"raw_text"}) if mandate is not None else "none"
    return hashlib.sha256(f"{body}|{revision}".encode()).hexdigest()[:16]


@dataclass
class Draft:
    id: str
    account: str
    client: str  # who opened it (socket peer); revisions from anyone else get the same 404 as an unknown id
    texts: list[str]  # every revision's text, for the audit trail (refused injection attempts stay visible)
    parse: ParseOutcome
    suggested: Mandate | None  # the order shown to the user (parsed + profile constraints); what /propose runs
    personalization: Any  # api.mandate.Personalization; typed loosely to keep deps free of router models
    revision: int
    version: str
    created: float
    confirmed: bool = False
    consumed: bool = False  # already handed to /propose once

    @property
    def text(self) -> str:
        return self.texts[-1]


class DraftCache:
    """Mirrors ProposalCache's shape (in-memory, bounded, expiring, thread-safe) for the confirm/revise loop.

    Every /draft call is firewalled on its own (no trust carries over between revisions). What gets locked at
    /confirm is the structured Mandate the user was shown — never text that /propose would re-parse, because a
    second parse (an LLM especially) could produce a different order than the one approved, and the profile's
    constraints added at draft time are not in the text at all."""

    def __init__(self, ttl_s: float = DRAFT_TTL_S, max_items: int = MAX_DRAFTS, max_revisions: int = MAX_REVISIONS,
                 max_open_per_account: int = MAX_OPEN_DRAFTS_PER_ACCOUNT) -> None:
        self.ttl_s, self.max_items, self.max_revisions = ttl_s, max_items, max_revisions
        self.max_open_per_account = max_open_per_account
        self._items: dict[str, Draft] = {}
        self._lock = threading.Lock()

    def start(self, account: str, client: str, text: str, parse: ParseOutcome, suggested: Mandate | None,
              personalization: Any) -> Draft:
        with self._lock:
            self._evict()
            open_drafts = sum(1 for d in self._items.values() if d.account == account and not d.confirmed)
            if open_drafts >= self.max_open_per_account:
                raise HTTPException(429, f"too many open drafts ({self.max_open_per_account}); revise or confirm one, "
                                         "or wait for it to expire")
            did = uuid.uuid4().hex
            draft = Draft(id=did, account=account, client=client, texts=[text], parse=parse, suggested=suggested,
                          personalization=personalization, revision=0, version=draft_version(suggested, 0),
                          created=time.monotonic())
            self._items[did] = draft
            return draft

    def revise(self, draft_id: str, account: str, client: str, text: str, parse: ParseOutcome,
               suggested: Mandate | None, personalization: Any) -> Draft:
        with self._lock:
            self._evict()
            d = self._items.get(draft_id)
            if d is None or d.account != account or d.client != client:
                raise HTTPException(404, "unknown or expired draft")
            if d.confirmed:
                raise HTTPException(409, "this draft is already confirmed; start a new draft for further changes")
            if d.revision >= self.max_revisions:
                raise HTTPException(429, f"too many revisions ({self.max_revisions}); start a new draft or use /evaluate_options")
            d.revision += 1
            d.texts.append(text)
            d.parse, d.suggested, d.personalization = parse, suggested, personalization
            d.version = draft_version(suggested, d.revision)
            return d

    def get(self, draft_id: str) -> Draft | None:
        with self._lock:
            self._evict()
            return self._items.get(draft_id)

    def confirm(self, draft_id: str, account: str, version: str) -> Draft:
        """Atomically lock the exact version the user saw. Raises 404 / 409 / 422."""
        with self._lock:
            self._evict()
            d = self._items.get(draft_id)
            if d is None or d.account != account:
                raise HTTPException(404, "unknown or expired draft")
            if d.confirmed:
                raise HTTPException(409, "this draft is already confirmed")
            if not hmac.compare_digest(d.version.encode(), version.encode()):
                raise HTTPException(409, "the draft changed since you saw it; review the latest version and confirm that")
            if d.suggested is None or not d.parse.verdict.allowed:
                raise HTTPException(422, "this draft did not parse into an order; revise the text with /draft before confirming")
            d.confirmed = True
            return d

    def consume(self, draft_id: str, account: str) -> Mandate:
        """One-shot hand-off of the locked Mandate to /propose. Raises 404 / 409."""
        with self._lock:
            self._evict()
            d = self._items.get(draft_id)
            if d is None or d.account != account:
                raise HTTPException(404, "unknown or expired draft")
            if not d.confirmed:
                raise HTTPException(409, "draft not confirmed yet — call /api/mandate/confirm first")
            if d.consumed:
                raise HTTPException(409, "this confirmed draft was already proposed")
            assert d.suggested is not None  # confirm() refuses drafts without one
            d.consumed = True
            return d.suggested

    def _evict(self) -> None:
        now = time.monotonic()
        for did in [d for d, item in self._items.items() if now - item.created > self.ttl_s]:
            del self._items[did]
        while len(self._items) >= self.max_items:
            del self._items[next(iter(self._items))]


@dataclass(frozen=True)
class RateRule:
    limit: int
    window_s: float


RATE_RULES: dict[str, RateRule] = {
    "draft:start:account": RateRule(10, 600),  # new drafts per account per 10 min
    "draft:start:client": RateRule(20, 600),
    "draft:any:account": RateRule(30, 600),  # starts + revisions
    "draft:any:client": RateRule(60, 600),
    "confirm:account": RateRule(20, 600),
}
STRIKE_LIMIT = 3  # firewall refusals ...
STRIKE_WINDOW_S = 1800.0  # ... within 30 min ...
STRIKE_COOLDOWN_S = 900.0  # ... lock drafting for 15 min


def rate_limit_by_client() -> bool:
    """Demo default: budgets and strikes follow the ACCOUNT only, so judges sharing one venue Wi-Fi (one public
    IP) never lock each other out. Set TECC_RATELIMIT_BY_CLIENT=1 to also meter per client IP — the right
    setting once accounts are authenticated and the API faces the internet."""
    return os.environ.get("TECC_RATELIMIT_BY_CLIENT", "0") == "1"


class RateLimiter:
    """Sliding-window budgets plus an injection "strike" cooldown. Always keyed by account; also by client IP
    when `by_client` (see rate_limit_by_client). Checked before any parser or LLM call, so a flood never reaches
    a model. In-process: one worker only."""

    def __init__(self, rules: dict[str, RateRule] | None = None, now: Callable[[], float] = time.monotonic,
                 by_client: bool | None = None) -> None:
        self.rules = rules or RATE_RULES
        self.by_client = rate_limit_by_client() if by_client is None else by_client
        self._now = now
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._strikes: dict[str, deque[float]] = {}
        self._cooldown_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, bucket: str, key: str) -> None:
        """Consume one hit from `bucket` for `key`, or raise 429 with Retry-After."""
        rule = self.rules[bucket]
        with self._lock:
            now = self._now()
            until = self._cooldown_until.get(key, 0.0)
            if until > now:
                raise HTTPException(429, "temporarily locked after repeated refused requests",
                                    headers={"Retry-After": str(int(until - now) + 1)})
            hits = self._hits.setdefault((bucket, key), deque())
            while hits and now - hits[0] >= rule.window_s:
                hits.popleft()
            if len(hits) >= rule.limit:
                raise HTTPException(429, "rate limit exceeded; slow down",
                                    headers={"Retry-After": str(int(rule.window_s - (now - hits[0])) + 1)})
            hits.append(now)

    def keys(self, account: str, client: str) -> list[str]:
        """The identities a request is metered under."""
        return [account, client] if self.by_client else [account]

    def strike(self, *keys: str) -> None:
        """Record a firewall refusal; STRIKE_LIMIT of them inside the window locks every key for the cooldown."""
        with self._lock:
            now = self._now()
            for key in keys:
                strikes = self._strikes.setdefault(key, deque())
                while strikes and now - strikes[0] >= STRIKE_WINDOW_S:
                    strikes.popleft()
                strikes.append(now)
                if len(strikes) >= STRIKE_LIMIT:
                    self._cooldown_until[key] = now + STRIKE_COOLDOWN_S
                    strikes.clear()


def client_key(request: Request) -> str:
    return "client:" + (request.client.host if request.client else "unknown")


@lru_cache(maxsize=1)
def _store() -> ProfileStore:
    return ProfileStore()


@lru_cache(maxsize=1)
def _proposals() -> ProposalCache:
    return ProposalCache()


@lru_cache(maxsize=1)
def _drafts() -> DraftCache:
    return DraftCache()


def get_store() -> ProfileStore:
    return _store()


def get_proposals() -> ProposalCache:
    return _proposals()


def get_drafts() -> DraftCache:
    return _drafts()


@lru_cache(maxsize=1)
def _limiter() -> RateLimiter:
    return RateLimiter()


def get_limiter() -> RateLimiter:
    return _limiter()


@lru_cache(maxsize=1)
def _news_sentinel() -> NewsRiskSentinel:
    return NewsRiskSentinel(ref=get_ref())


def get_news_sentinel() -> NewsRiskSentinel:
    """Agent 1 for the free-text path: CMC Fear & Greed + Grok + CoinGlass + FinBERT. Each source falls back to
    an offline neutral/lexicon reading when its key (CMC_API_KEY, GROK_API_KEY, COINGLASS_API_KEY) is unset."""
    return _news_sentinel()


@lru_cache(maxsize=1)
def _anchors() -> AuditAnchorService:
    return AuditAnchorService.from_env()


def get_anchors() -> AuditAnchorService:
    """Anchors audit hashes on FISCO BCOS when TECC_AUDIT_ANCHOR_* is configured; otherwise reports not_configured."""
    return _anchors()


@lru_cache(maxsize=1)
def _router() -> MarketRouter:
    from tecc_brain.onchain.markets import build_router

    router = build_router()
    router.anchors = get_anchors()
    return router


def get_router() -> MarketRouter:
    """The one MarketRouter every execution path shares, so the cross-chain tether tracker sees all spending.
    Markets with a deployed vault (scripts/deploy_market_chain.py) are live; the others are honest simulations."""
    return _router()


@dataclass
class RouterExecutor:
    """Adapts the MarketRouter to the graph's Executor protocol, metering against this request's vault radius."""

    router: MarketRouter
    limit_usd: float

    def submit(self, intent: ExecutionIntent, account: str) -> ExecutionIntent:
        return self.router.submit(intent, account, limit_usd=self.limit_usd)


@lru_cache(maxsize=1)
def _brain_llm() -> BrainLLM | None:
    return brain_llm_from_env()


def get_brain_llm() -> BrainLLM | None:
    """The AI Brain's model, or None (rule-based BrainReport). Tests override this with a fake."""
    return _brain_llm()


@lru_cache(maxsize=1)
def get_ref() -> Reference:
    return load_reference()


LOOPBACK = frozenset({"127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost", "testclient"})  # socket peers; a network peer is always a real IP
LOCAL_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1", "testserver"})


def allowed_origins() -> list[str]:
    raw = os.environ.get("TECC_CORS_ORIGINS", "")
    origins = []
    for o in raw.split(","):
        o = o.strip()
        if not o:
            continue
        try:
            from urllib.parse import urlparse
            u = urlparse(o)
            if u.scheme and u.netloc:
                origins.append(f"{u.scheme}://{u.netloc}")
            else:
                origins.append(o)
        except Exception:
            origins.append(o)
    defaults = [
        "https://www.tec-c.xyz",
        "https://tec-c.xyz",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "null",
    ]
    for d in defaults:
        if d not in origins:
            origins.append(d)
    return origins


def _hostname(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):  # [::1]:8000
        return host[1:host.index("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def require_client(request: Request) -> None:
    """Who may drive the Brain. With TECC_API_TOKEN set, every /api call needs `Authorization: Bearer <token>`.
    Without it the API serves this machine only:
      * the socket peer must be loopback (no other machine);
      * the Host header must be a local name (defeats DNS rebinding: evil.com resolving to 127.0.0.1);
      * a browser Origin, when sent, must be an allowed frontend origin (defeats cross-site POSTs / CSRF).

    The vault stays the real authority: nothing here can sign or move funds, and every on-chain action is still
    checked by TetherGuardHook. This gate protects the learned profile and proposals.
    """
    token = os.environ.get("TECC_API_TOKEN")
    if token:
        given = request.headers.get("authorization", "")
        if not hmac.compare_digest(given.encode(), f"Bearer {token}".encode()):
            raise HTTPException(401, "missing or wrong API token")
        return
    host = request.client.host if request.client else ""
    req_host = _hostname(request.headers.get("host", ""))
    is_tunnel_host = req_host.endswith(".trycloudflare.com") or req_host.endswith(".trycloudflare.co")
    if host not in LOOPBACK and not is_tunnel_host:
        raise HTTPException(403, f"the Brain API only answers this machine (client={host}) unless TECC_API_TOKEN is set")
    extra = {h.strip().lower() for h in os.environ.get("TECC_ALLOWED_HOSTS", "").split(",") if h.strip()}
    is_valid_host = (
        req_host in LOCAL_HOSTNAMES
        or req_host in extra
        or is_tunnel_host
    )
    if not is_valid_host:
        raise HTTPException(403, "unexpected Host header")
    origin = request.headers.get("origin")
    same_origin = origin == f"{request.url.scheme}://{request.headers.get('host', '')}"
    is_loopback_origin = False
    if origin:
        if origin == "null":
            is_loopback_origin = True
        else:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(origin)
                if parsed.hostname in LOCAL_HOSTNAMES:
                    is_loopback_origin = True
            except Exception:
                pass
    is_trusted_domain = False
    if origin:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(origin)
            h = (parsed.hostname or "").lower()
            if h == "tec-c.xyz" or h.endswith(".tec-c.xyz") or h.endswith(".trycloudflare.com"):
                is_trusted_domain = True
        except Exception:
            pass
    if origin is not None and not same_origin and not is_loopback_origin and not is_trusted_domain and origin not in allowed_origins():
        raise HTTPException(403, "cross-site request refused")

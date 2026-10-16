"""Typed domain models shared by every layer of the Brain.

UNIT CONVENTION (applies to every field below unless its description says otherwise):

* Rates — APY, hurdle, PD, edges, scores — are **fractions per year**: 0.0215 means 2.15 %/yr.
  Convert to percent only when displaying.
* Money is **float USD**. The vault (TetherGuardHook) measures the Tether Radius in **8-decimal USD**
  (Chainlink normalised); convert only at the chain boundary with :func:`usd_to_onchain` /
  :func:`onchain_to_usd`. Never pass wei or USD×1e8 into the risk engine.
* Probabilities are in [0, 1].
* Prices of pegged assets are in **peg units** (USDC 0.88 means 0.88 USD; stETH 0.94 means 0.94 ETH).
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from enum import Enum, IntEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ONCHAIN_USD_DECIMALS = 8


def usd_to_onchain(usd: float) -> int:
    """Float USD -> 8-decimal USD integer used by TetherGuardHook (round half-even)."""
    scaled = Decimal(str(usd)) * (Decimal(10) ** ONCHAIN_USD_DECIMALS)
    return int(scaled.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def onchain_to_usd(value: int) -> float:
    """8-decimal USD integer from TetherGuardHook -> float USD."""
    return float(Decimal(value) / (Decimal(10) ** ONCHAIN_USD_DECIMALS))


Fraction = Field(ge=0.0, le=1.0)


# --- Enums -------------------------------------------------------------------------------------


class RiskTier(IntEnum):
    """Matches TetherGuardHook RISK_TIER_* constants."""

    CONSERVATIVE = 1
    BALANCED = 2
    AGGRESSIVE = 3


class ActionType(str, Enum):
    STAKE = "stake"
    DEPOSIT = "deposit"
    OPTIMIZE_YIELD = "optimize_yield"
    SWAP = "swap"
    WITHDRAW = "withdraw"
    TRANSFER = "transfer"
    REDUCE_EXPOSURE = "reduce_exposure"
    BUY_DISCOUNT = "buy_discount"


class AssetKind(str, Enum):
    NATIVE = "native"
    STABLE_FIAT = "stable_fiat"
    STABLE_CRYPTO = "stable_crypto"
    STABLE_ALGORITHMIC = "stable_algorithmic"
    LST = "lst"
    GOLD = "gold"
    BTC_WRAPPED = "btc_wrapped"


class AutonomyMode(str, Enum):
    AUTO = "AUTO"
    PROPOSE = "PROPOSE"
    BREAKOUT = "BREAKOUT"
    BLOCKED = "BLOCKED"


class CardLabel(str, Enum):
    GOOD = "GOOD"
    BETTER = "BETTER"
    BEST = "BEST"
    REDUCE_EXPOSURE = "REDUCE_EXPOSURE"
    OPPORTUNITY = "OPPORTUNITY"


REDEMPTION_OPEN = 0.0
REDEMPTION_DELAYED = 0.5
REDEMPTION_PAUSED = 1.0
_REDEMPTION_VALUES = {REDEMPTION_OPEN, REDEMPTION_DELAYED, REDEMPTION_PAUSED}

Peg = Literal["USD", "ETH", "XAU"]

_STATIC = ConfigDict(frozen=True, extra="forbid")


# --- Static reference data ---------------------------------------------------------------------


class Asset(BaseModel):
    """A token the Brain can hold or reason about (static, from data/assets.json)."""

    model_config = _STATIC

    symbol: str
    name: str
    kind: AssetKind
    peg: Peg | None = None
    tier: RiskTier
    cluster: str | None = Field(None, description="Contagion cluster id, e.g. usd_fiat")
    reserve_quality: float = Field(1.0, ge=0, le=1, description="q: share of value left if the peg mechanism fails")
    lgd: float = Field(0.0, ge=0, le=1, description="Loss given impairment, fraction of position")
    pd_base: float = Field(0.0, ge=0, le=1, description="Baseline annual probability of permanent impairment")
    redemption_fee: float = Field(0.0, ge=0, le=0.05, description="Fraction charged on redemption")
    redemption_delay_days: float = Field(0.0, ge=0)
    coverage_default: float = Field(
        1.0, ge=0, le=1.5, description="Claim per token honoured by the redemption mechanism (BRAIN_DESIGN §2.4)"
    )
    note: str = ""


class Venue(BaseModel):
    """A place money can go: a protocol position the Brain can propose (static, data/venues.json)."""

    model_config = _STATIC

    id: str
    name: str
    protocol: str
    action: ActionType
    accepts: list[str] = Field(min_length=1, description="Asset symbols that can be deposited")
    produces: str | None = Field(None, description="Asset symbol received, if any")
    tier: RiskTier
    pd_base: float = Field(ge=0, le=1, description="Annual probability of permanent impairment of the venue")
    lgd: float = Field(ge=0, le=1, description="Loss given impairment, fraction of position")
    entry_slippage_bps: float = Field(0.0, ge=0, description="Normal-conditions entry cost, basis points")
    exit_slippage_bps: float = Field(0.0, ge=0, description="Normal-conditions exit slippage, basis points")
    redemption_delay_days: float = Field(0.0, ge=0, description="Wait before exit proceeds are available")
    exposures: list[str] = Field(default_factory=list, description="Pegged assets this position depends on")
    target_address: str | None = Field(None, description="On-chain target, filled at deployment (Phase 7)")
    note: str = ""


class ContagionLink(BaseModel):
    """Directed link: distress in `source` raises failure risk of `target` by rho (BRAIN_DESIGN §2.5)."""

    model_config = _STATIC

    source: str
    target: str
    rho: float = Field(ge=0, le=1)
    note: str = ""


# --- Market inputs -----------------------------------------------------------------------------


class PegState(BaseModel):
    """Live state of a pegged asset — the inputs of the regime model (BRAIN_DESIGN §2.4)."""

    model_config = _STATIC

    symbol: str
    price: float = Field(gt=0, description="Price in peg units")
    sentiment_negative: float = Field(0.0, ge=0, le=1, description="FinBERT P(negative) for matched entity")
    redemption_status: float = Field(REDEMPTION_OPEN, description="0 open, 0.5 delayed/limited, 1 paused")
    liquidity_stress: float = Field(0.0, ge=0, le=1, description="Pool imbalance / depth drop vs 7-day avg")
    coverage: float = Field(1.0, ge=0, le=1.5, description="Claim per token honoured by redemption")
    source: str = "unknown"
    as_of: datetime | None = None

    @field_validator("redemption_status")
    @classmethod
    def _known_redemption_status(cls, value: float) -> float:
        if value not in _REDEMPTION_VALUES:
            raise ValueError("redemption_status must be 0 (open), 0.5 (delayed) or 1 (paused)")
        return value


class VenueQuote(BaseModel):
    model_config = _STATIC

    venue_id: str
    apy: float = Field(ge=-1, le=10, description="Fraction per year")
    depth_usd: float = Field(ge=0)
    source: str = "unknown"
    as_of: datetime | None = None


class NewsSignal(BaseModel):
    model_config = _STATIC

    entity: str
    p_negative: float = Field(ge=0, le=1)
    headline: str
    source: str = "unknown"


class MarketSnapshot(BaseModel):
    """Everything the risk engine reads about the market at one moment."""

    model_config = _STATIC

    as_of: datetime
    hurdle_rate: float = Field(ge=-0.05, le=0.5, description="1Y Shibor, fraction per year")
    shibor: dict[str, float] = Field(default_factory=dict, description="Tenor -> fraction per year")
    prices_usd: dict[str, float] = Field(default_factory=dict)
    venues: dict[str, VenueQuote] = Field(default_factory=dict)
    pegs: dict[str, PegState] = Field(default_factory=dict)
    news: list[NewsSignal] = Field(default_factory=list)
    source: str


# --- Portfolio ---------------------------------------------------------------------------------


class Position(BaseModel):
    """A holding: a raw asset in the vault (venue_id None) or a position in a venue."""

    asset: str
    venue_id: str | None = None
    amount_usd: float = Field(ge=0)


class Portfolio(BaseModel):
    account: str
    positions: list[Position] = Field(default_factory=list)

    @property
    def nav_usd(self) -> float:
        return sum(p.amount_usd for p in self.positions)


# --- User profile and vault state --------------------------------------------------------------

# Minimum posterior approval probability before the Brain may act alone, by tier (BRAIN_DESIGN §2.3).
APPROVAL_THRESHOLDS: dict[RiskTier, float] = {
    RiskTier.CONSERVATIVE: 0.80,
    RiskTier.BALANCED: 0.70,
    RiskTier.AGGRESSIVE: 0.60,
}
APPROVAL_PRIOR = (2.0, 2.0)  # Beta(2, 2): no opinion, weak

# Loss aversion λ: where each tier starts and the band learning can never leave (BRAIN_DESIGN §2.2).
LAMBDA_START: dict[RiskTier, float] = {
    RiskTier.CONSERVATIVE: 3.0,
    RiskTier.BALANCED: 1.0,
    RiskTier.AGGRESSIVE: 0.3,
}
LAMBDA_BANDS: dict[RiskTier, tuple[float, float]] = {
    RiskTier.CONSERVATIVE: (2.0, 5.0),
    RiskTier.BALANCED: (0.5, 2.0),
    RiskTier.AGGRESSIVE: (0.0, 0.8),
}


class Signal(str, Enum):
    """A review signal: an on-chain Morning Review event or an explicit UI choice (BRAIN_DESIGN §3.2)."""

    RATIFY = "ratify"  # TransactionRatified
    FLAG = "flag"  # TransactionFlaggedForRevert
    NOTE_PENALTY = "note_penalty"  # TransactionNoteSubmitted(penalizeBrain=true)
    NOTE = "note"  # TransactionNoteSubmitted(penalizeBrain=false)
    BREAKOUT_ACCEPT = "breakout_accept"  # SignApprovalSubmitted(true)
    BREAKOUT_REJECT = "breakout_reject"  # SignApprovalSubmitted(false)
    PICK_SAFER = "pick_safer"  # UI: chose a safer card than BEST
    PICK_RISKIER = "pick_riskier"  # UI: chose a riskier card than BETTER (incl. a de-peg opportunity)
    IGNORED = "ignored"  # proposal left unanswered for 24 h


class FeedbackEvent(BaseModel):
    """One review signal. `event_id` makes learning idempotent (e.g. tx hash + log index, or record id + kind)."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(min_length=1, max_length=200)
    signal: Signal
    venue_id: str | None = None
    amount_usd: float = Field(0.0, ge=0)
    at: datetime
    note: str = Field("", max_length=1000)

    @field_validator("at")
    @classmethod
    def _timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("event time must be timezone-aware (UTC)")
        return value


class BrainProfile(BaseModel):
    """What the Brain has learned about one user (Phase 5 adds the update rules and persistence)."""

    account: str
    tier: RiskTier
    lam: float = Field(ge=0, description="Loss aversion λ: expected loss is weighted (1 + λ)")
    tau: float = Field(0.6, ge=0, le=1, description="Brain trust τ: scales the soft tether")
    approvals: dict[str, tuple[float, float]] = Field(
        default_factory=dict, description="venue_id -> Beta(alpha, beta) of the user approving the Brain's trades"
    )
    note: str = ""
    # Learning state (Phase 5): written only by tecc_brain.learning.
    updated_at: datetime | None = None
    tau_gains: dict[str, float] = Field(default_factory=dict, description="UTC date -> trust gained that day (daily cap)")
    history: list[FeedbackEvent] = Field(default_factory=list, description="Signals from the last 90 days")
    seen_events: list[str] = Field(default_factory=list, description="Applied event ids, so a re-sync is harmless")

    def _beta(self, venue_id: str) -> tuple[float, float]:
        return self.approvals.get(venue_id, APPROVAL_PRIOR)

    def approval_mean(self, venue_id: str) -> float:
        alpha, beta = self._beta(venue_id)
        return alpha / (alpha + beta)

    def has_history(self, venue_id: str) -> bool:
        alpha, beta = self._beta(venue_id)
        return alpha + beta > sum(APPROVAL_PRIOR)

    def affinity(self, venue_id: str) -> float:
        """−1 … +1 learned like/dislike; 0 without history."""
        return 2.0 * self.approval_mean(venue_id) - 1.0 if self.has_history(venue_id) else 0.0


class VaultState(BaseModel):
    """What the Brain knows about the on-chain vault right now (Phase 7 reads it from TetherGuardHook)."""

    tether_radius_usd: float = Field(ge=0)
    spent_today_usd: float = Field(0.0, ge=0)
    heartbeat_alive: bool = True
    whitelist: set[str] | None = None

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.tether_radius_usd - self.spent_today_usd)


# --- Intent and decision contracts -------------------------------------------------------------


class Mandate(BaseModel):
    """A user's request, parsed into typed form."""

    raw_text: str
    action: ActionType
    asset: str
    amount: float = Field(ge=0, description="In units of `asset`")
    amount_usd: float | None = Field(None, ge=0)
    horizon_days: int = Field(365, gt=0)
    recipients: list[str] = Field(default_factory=list, description="Must stay empty unless whitelisted")
    constraints: list[str] = Field(default_factory=list)
    parser: Literal["rules", "llm"] = "rules"


class ScoreBreakdown(BaseModel):
    """Every term of score = excess − (1+λ)·PD·LGD − c_in − c_out_stress + w_a·a, fractions per year."""

    excess_yield: float
    pd: float = Field(ge=0, le=1)
    lgd: float = Field(ge=0, le=1)
    expected_loss: float
    loss_weighted: float
    c_in: float
    c_out_stress: float
    affinity_term: float = 0.0
    total: float


class Candidate(BaseModel):
    venue_id: str = Field(description="Destination venue id, or asset symbol for exits/discount buys")
    from_venue_id: str | None = Field(None, description="Venue being exited, for reduce-exposure moves")
    action: ActionType
    asset_in: str
    amount_usd: float = Field(ge=0)
    apy: float
    score: ScoreBreakdown | None = None
    rejected_reasons: list[str] = Field(default_factory=list)


class Card(BaseModel):
    label: CardLabel
    candidate: Candidate
    mode: AutonomyMode
    headline: str
    explanation: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    mandate: Mandate
    mode: AutonomyMode
    auto_amount_usd: float = Field(0.0, ge=0)
    proposed_amount_usd: float = Field(0.0, ge=0)
    cards: list[Card] = Field(default_factory=list)
    rejected: list[Candidate] = Field(default_factory=list, description="Candidates removed by hard filters, with reasons")
    trace: list[str] = Field(default_factory=list)

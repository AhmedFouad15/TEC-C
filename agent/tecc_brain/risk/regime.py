"""Fundamental fair value and the 3-regime peg model (BRAIN_DESIGN §2.4).

The question is not "is the news bad?" but "is this a temporary mispricing or a permanent capital impairment?".
We never extrapolate historical mean-reversion speed: recovery is inferred from whether the peg mechanism still
works (redemptions open, reserves intact, liquidity returning).

The logit coefficients below are hand-set and validated against the reference episodes in data/episodes.json
(USDC-SVB 2023, stETH-Celsius 2022, UST 2022, a normal day). Fitting them on more events is future work.
"""

from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tecc_brain.models import Asset, PegState

# z_distress = DISTRESS_BIAS + DISTRESS_GAP·min(gap, GAP_CAP) + DISTRESS_SENTIMENT·s + DISTRESS_LIQUIDITY·L + DISTRESS_CONTAGION·k
DISTRESS_BIAS = -4.0
DISTRESS_GAP = 60.0
DISTRESS_GAP_CAP = 0.08  # gaps beyond 8% are not "temporary" — distress stops gaining, failure keeps rising
DISTRESS_SENTIMENT = 2.0
DISTRESS_LIQUIDITY = 3.0
DISTRESS_CONTAGION = 2.0

# z_failure = FAILURE_BIAS + FAILURE_GAP·gap + FAILURE_SENTIMENT·s + FAILURE_REDEMPTION·R + FAILURE_QUALITY·(1−q) + FAILURE_CONTAGION·k
FAILURE_BIAS = -7.0
FAILURE_GAP = 30.0
FAILURE_SENTIMENT = 3.0
FAILURE_REDEMPTION = 4.0
FAILURE_QUALITY = 4.0
FAILURE_CONTAGION = 3.0

Regime = Literal["normal", "distress", "failure"]


class RegimeProbs(BaseModel):
    model_config = ConfigDict(frozen=True)

    p_normal: float = Field(ge=0, le=1)
    p_distress: float = Field(ge=0, le=1)
    p_failure: float = Field(ge=0, le=1)
    z_distress: float
    z_failure: float

    @property
    def dominant(self) -> Regime:
        ranked = {"normal": self.p_normal, "distress": self.p_distress, "failure": self.p_failure}
        return max(ranked, key=ranked.__getitem__)  # type: ignore[return-value]

    @property
    def p_recover(self) -> float:
        """Probability the peg mechanism still works (normal or temporary distress)."""
        return self.p_normal + self.p_distress


class PegAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    price: float
    fair_value: float
    gap: float = Field(description="Distance below peg, 1 − price (0 when at or above peg)")
    discount_to_fv: float = Field(description="(FV − price) / FV; positive = trading below fundamental value")
    probs: RegimeProbs
    failure_excess: float = Field(description="p_failure above the asset's quiet-state floor (avoids double counting pd_base)")


def fair_value(coverage: float, redemption_fee: float, redemption_delay_days: float, hurdle: float) -> float:
    """FV = coverage × (1 − fee) / (1 + hurdle × delay_years): what a redemption is worth today."""
    return coverage * (1.0 - redemption_fee) / (1.0 + hurdle * redemption_delay_days / 365.0)


def regime_probabilities(
    *,
    gap: float,
    sentiment: float,
    redemption: float,
    quality: float,
    liquidity_stress: float,
    contagion: float = 0.0,
) -> RegimeProbs:
    gap = max(0.0, gap)
    z_distress = (
        DISTRESS_BIAS
        + DISTRESS_GAP * min(gap, DISTRESS_GAP_CAP)
        + DISTRESS_SENTIMENT * sentiment
        + DISTRESS_LIQUIDITY * liquidity_stress
        + DISTRESS_CONTAGION * contagion
    )
    z_failure = (
        FAILURE_BIAS
        + FAILURE_GAP * gap
        + FAILURE_SENTIMENT * sentiment
        + FAILURE_REDEMPTION * redemption
        + FAILURE_QUALITY * (1.0 - quality)
        + FAILURE_CONTAGION * contagion
    )
    logits = (0.0, z_distress, z_failure)
    top = max(logits)
    weights = [math.exp(z - top) for z in logits]
    total = sum(weights)
    p_normal, p_distress, p_failure = (w / total for w in weights)
    return RegimeProbs(
        p_normal=p_normal,
        p_distress=p_distress,
        p_failure=p_failure,
        z_distress=z_distress,
        z_failure=z_failure,
    )


def quiet_failure_floor(quality: float) -> float:
    """p_failure on a perfectly calm day; already priced into the asset's annual pd_base."""
    return regime_probabilities(gap=0.0, sentiment=0.0, redemption=0.0, quality=quality, liquidity_stress=0.0).p_failure


def assess_peg(peg: PegState, asset: Asset, hurdle: float, contagion: float = 0.0) -> PegAssessment:
    fv = fair_value(peg.coverage, asset.redemption_fee, asset.redemption_delay_days, hurdle)
    gap = max(0.0, 1.0 - peg.price)
    probs = regime_probabilities(
        gap=gap,
        sentiment=peg.sentiment_negative,
        redemption=peg.redemption_status,
        quality=asset.reserve_quality,
        liquidity_stress=peg.liquidity_stress,
        contagion=contagion,
    )
    return PegAssessment(
        symbol=peg.symbol,
        price=peg.price,
        fair_value=fv,
        gap=gap,
        discount_to_fv=(fv - peg.price) / fv if fv > 0 else 0.0,
        probs=probs,
        failure_excess=max(0.0, probs.p_failure - quiet_failure_floor(asset.reserve_quality)),
    )

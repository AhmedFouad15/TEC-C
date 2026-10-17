"""PegGuard: A Regime-Switching, Recovery-Risk-Adjusted Quantitative Arbitrage & Multi-Modal
Microstructure Framework for Pegged, Staked, and Tokenized Assets.

Implements the complete 5-layer architecture specified in PegGuard.pdf:
- Layer 1: Dual-Anchor Fair-Value (FV_fund) & Multi-Horizon Equilibrium Calibration (mu_mkt, R_cons, Baseline*)
- Layer 2: 3-Regime Markov-Switching Duration & Deterministic <15ms Closed-Form AR(1) OLS Engine
- Layer 3: Recovery-Risk EV & Signed Perpetual Funding Gate (+15 bps HurdleRule)
- Layer 4: Stateful Asset-Specific Token Check (50% FinBERT + Hard Veto, 30% On-Chain/Spot Flow, 20% Grok)
- Layer 5: Asset-Specific Hedging (Class A Short Perp vs Class B FISCO BCOS Par-Capped USDT Repo)
           & Cross-Stablecoin Contagion Matrix (beta_ij) with Convex Position Sizing.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import IntEnum
import math
from typing import Any, Literal

from pydantic import BaseModel, Field

# =============================================================================
# Constants & Canonical Parameters (PegGuard.pdf)
# =============================================================================

DEFAULT_HURDLE_RATE_BPS = 15.0  # +15 bps minimum Recovery-Adjusted EV
DEFAULT_HURDLE_RATE = DEFAULT_HURDLE_RATE_BPS / 10_000.0  # 0.0015
FINBERT_INSOLVENCY_VETO_THRESHOLD = 0.60  # P(Insolvency | FinBERT) >= 0.60 -> I_SafeVeto = 0

# Layer 4 Pillar Weights (PegGuard.pdf Page 6)
LAYER4_FINBERT_WEIGHT = 0.50
LAYER4_MICROSTRUCTURE_WEIGHT = 0.30
LAYER4_GROK_WEIGHT = 0.20

# Default Cross-Stablecoin Contagion Exposure Matrix beta_ij (PegGuard.pdf Page 7)
# Measures reserve overlap and Curve 3pool / DeFi liquidity co-dependency across pegged assets (i, j).
DEFAULT_CONTAGION_MATRIX: dict[str, dict[str, float]] = {
    "USDC": {"DAI": 0.45, "FRAX": 0.40, "USDT": 0.20, "FDUSD": 0.15},
    "DAI": {"USDC": 0.65, "FRAX": 0.45, "USDT": 0.25, "stETH": 0.20},
    "FRAX": {"USDC": 0.60, "DAI": 0.45, "USDT": 0.25},
    "USDT": {"USDC": 0.20, "DAI": 0.20, "FDUSD": 0.25},
    "FDUSD": {"USDC": 0.25, "USDT": 0.30},
    "stETH": {"WBETH": 0.35, "rETH": 0.30, "ezETH": 0.40},
    "WBETH": {"stETH": 0.35, "rETH": 0.25},
    "rETH": {"stETH": 0.30, "WBETH": 0.25},
    "ezETH": {"stETH": 0.45, "rETH": 0.25},
    "PAXG": {"XAUT": 0.30},
    "XAUT": {"PAXG": 0.30},
}

CRYPTO_PEGGED_ASSETS = {"stETH", "WBETH", "rETH", "ezETH"}
FIAT_PEGGED_STABLECOINS = {"USDC", "USDT", "DAI", "FRAX", "FDUSD", "UST"}


class PegRegime(IntEnum):
    """Latent states S_t in {1, 2, 3} (PegGuard.pdf Page 5)."""

    NORMAL_MICROSTRUCTURE = 1  # S_t = 1: High reversion speed (theta_1 >> 0), low sigma_1, rapid half-life
    TEMPORARY_LIQUIDITY_DISTRESS = 2  # S_t = 2: Reserves solvent (FV_fund ~ 1), order books depleted
    FUNDAMENTAL_PEG_COLLAPSE = 3  # S_t = 3: Reserve insolvency or non-stationary divergence (beta >= 1.0)


HedgeClass = Literal["CLASS_A_CRYPTO_PERP", "CLASS_B_FISCO_PAR_REPO"]


# =============================================================================
# Layer 1: Dual-Anchor Fair-Value & Multi-Horizon Equilibrium Calibration
# =============================================================================


class Layer1Input(BaseModel):
    """Inputs for Layer 1 Calibration (PegGuard.pdf Page 4)."""

    symbol: str = "USDC"
    p_par: float = Field(1.000, gt=0, description="Theoretical par value P_par")
    liquid_reserves: float = Field(1.0, ge=0, description="Verifiable liquid reserves LiquidReserves_t")
    circulating_supply: float = Field(1.0, gt=0, description="Circulating supply CirculatingSupply_t")
    y_asset: float = Field(0.0, description="Annualized asset staking/collateral yield y_asset")
    r_fee: float = Field(0.001, ge=0, description="Primary redemption fee r_fee")
    c_illiquidity: float = Field(0.0, ge=0, description="Illiquidity friction rate c_illiquidity")
    tau_redeem_days: float = Field(1.0, ge=0, description="Primary settlement delay tau_redeem in days")

    # Dual-path spot triangulation inputs
    r_direct: float = Field(0.90, gt=0, description="Direct spot ratio R_direct(t) (e.g. WBETH/ETH or USDC/USD)")
    p_pegged_usdt: float = Field(0.90, gt=0, description="Cross-leg P_pegged/USDT(t)")
    p_anchor_usdt: float = Field(1.00, gt=0, description="Anchor cross-leg P_anchor/USDT(t)")
    w_dir: float = Field(0.60, ge=0, le=1, description="Weight on direct spot book w_dir")

    # Multi-horizon rolling averages
    avg_1w: float = Field(0.998, gt=0, description="1-Week rolling average")
    avg_1m: float = Field(0.999, gt=0, description="1-Month rolling average")
    avg_1y: float = Field(1.000, gt=0, description="1-Year rolling average")
    w_1w: float = Field(0.50, ge=0, le=1)
    w_1m: float = Field(0.30, ge=0, le=1)
    w_1y: float = Field(0.20, ge=0, le=1)

    sigma_30d: float = Field(0.015, gt=0, description="30-day rolling volatility sigma_30D(t)")


class Layer1Result(BaseModel):
    """Outputs of Layer 1 Calibration (PegGuard.pdf Page 4)."""

    fv_fund: float = Field(description="Economic Fundamental Fair-Value Benchmark FV_fund(t)")
    reserve_ratio: float = Field(description="min(1, LiquidReserves_t / CirculatingSupply_t)")
    r_cons: float = Field(description="Dual-Path Spot Triangulation Consensus Ratio R_cons(t)")
    r_synthetic: float = Field(description="Synthetic cross-rate P_pegged/USDT(t) / P_anchor/USDT(t)")
    mu_mkt: float = Field(description="Multi-Horizon Market Consensus mu_mkt(t)")
    baseline_star: float = Field(description="Conservative Dual-Anchor Baseline*(t) = min(FV_fund, mu_mkt)")
    abnormal_spread_delta: float = Field(description="Abnormal Spread delta(t) = R_cons(t) - Baseline*(t)")
    z_score: float = Field(description="Standardized dislocation Z(t) = delta(t) / sigma_30D(t)")


def compute_fundamental_fair_value(
    p_par: float,
    liquid_reserves: float,
    circulating_supply: float,
    y_asset: float = 0.0,
    r_fee: float = 0.0,
    c_illiquidity: float = 0.0,
    tau_redeem_days: float = 0.0,
) -> tuple[float, float]:
    """Computes Economic Fundamental Fair-Value Benchmark FV_fund(t) (PegGuard.pdf Page 4):

    FV_fund(t) = P_par * min(1, LiquidReserves_t / CirculatingSupply_t)
                 * exp[(y_asset - r_fee - c_illiquidity) * tau_redeem]
    """
    reserve_ratio = min(1.0, max(0.0, liquid_reserves / max(circulating_supply, 1e-12)))
    tau_years = max(0.0, tau_redeem_days) / 365.0
    exponent = max(-20.0, min(1.0, (y_asset - r_fee - c_illiquidity) * tau_years))
    carry_factor = math.exp(exponent)
    fv_fund = p_par * reserve_ratio * carry_factor
    return round(fv_fund, 6), round(reserve_ratio, 6)


def calibrate_layer1(inp: Layer1Input) -> Layer1Result:
    """Executes Layer 1: Dual-Anchor Fair-Value & Multi-Horizon Equilibrium Calibration."""
    fv_fund, reserve_ratio = compute_fundamental_fair_value(
        p_par=inp.p_par,
        liquid_reserves=inp.liquid_reserves,
        circulating_supply=inp.circulating_supply,
        y_asset=inp.y_asset,
        r_fee=inp.r_fee,
        c_illiquidity=inp.c_illiquidity,
        tau_redeem_days=inp.tau_redeem_days,
    )
    r_synthetic = inp.p_pegged_usdt / max(inp.p_anchor_usdt, 1e-12)
    r_cons = inp.w_dir * inp.r_direct + (1.0 - inp.w_dir) * r_synthetic

    w_sum = inp.w_1w + inp.w_1m + inp.w_1y
    if w_sum <= 0:
        mu_mkt = inp.avg_1m
    else:
        mu_mkt = (inp.w_1w * inp.avg_1w + inp.w_1m * inp.avg_1m + inp.w_1y * inp.avg_1y) / w_sum

    baseline_star = min(fv_fund, mu_mkt)
    delta = r_cons - baseline_star
    z_score = delta / max(inp.sigma_30d, 1e-8)

    return Layer1Result(
        fv_fund=round(fv_fund, 6),
        reserve_ratio=round(reserve_ratio, 6),
        r_cons=round(r_cons, 6),
        r_synthetic=round(r_synthetic, 6),
        mu_mkt=round(mu_mkt, 6),
        baseline_star=round(baseline_star, 6),
        abnormal_spread_delta=round(delta, 6),
        z_score=round(z_score, 4),
    )


# =============================================================================
# Layer 2: 3-Regime Markov-Switching Duration & Fast OLS Fallback
# =============================================================================


class OLSFitResult(BaseModel):
    """Closed-Form AR(1) OLS Engine result: Delta_delta_t = alpha + kappa * delta_{t-1} + eps_t."""

    alpha: float
    kappa: float
    beta: float = Field(description="Autoregressive persistence beta = 1 + kappa")
    theta_ols: float = Field(description="Mean-reversion speed theta_OLS = -ln(1 + kappa) / dt (per hour)")
    theta_se: float = Field(description="Delta-method standard error of theta_OLS")
    residual_sigma: float
    death_spiral_canary: bool = Field(description="True if beta = 1 + kappa >= 1.0 (non-stationary divergence)")


class Layer2Result(BaseModel):
    """Outputs of Layer 2: 3-Regime Markov-Switching Duration & Fast OLS Fallback (PegGuard.pdf Page 5)."""

    regime: PegRegime = Field(description="Active latent regime S_t in {1, 2, 3}")
    regime_name: str
    p_regime_1_normal: float = Field(ge=0, le=1)
    p_regime_2_distress: float = Field(ge=0, le=1)
    p_regime_3_collapse: float = Field(ge=0, le=1)
    p_rec: float = Field(ge=0, le=1, description="Probability of Peg Recovery P_rec = P(S_t=1) + P(S_t=2)")
    ols: OLSFitResult
    theta_active: float = Field(description="Regime-conditioned reversion speed theta(S_t) per hour")
    half_life_hours: float = Field(description="t_{1/2}(S_t) = ln(2) / theta(S_t) in hours (inf if S_t=3)")
    expected_duration_hours: float = Field(description="Expected exposure duration T_exp(S_t) in hours")
    death_spiral_veto: bool = Field(description="True if S_t == 3 or beta >= 1.0")


def fit_ar1_ols(spread_series: list[float], dt_hours: float = 1.0) -> OLSFitResult:
    """Deterministic <15ms Closed-Form AR(1) OLS Engine (PegGuard.pdf Page 5):
    Fits Delta(delta_t) = alpha + kappa * delta_{t-1} + eps_t
    with Delta-method standard errors for theta_OLS = -ln(1 + kappa) / dt.
    """
    if not math.isfinite(dt_hours) or dt_hours <= 0 or any(not math.isfinite(x) for x in spread_series):
        return OLSFitResult(
            alpha=0.0,
            kappa=0.0,
            beta=1.0,
            theta_ols=0.0,
            theta_se=0.0,
            residual_sigma=0.0,
            death_spiral_canary=True,
        )

    n = len(spread_series)
    if n < 3:
        # Default stationary initializer when series is short
        kappa = -0.12
        beta = 1.0 + kappa
        theta_ols = -math.log(beta) / max(dt_hours, 1e-6)
        return OLSFitResult(
            alpha=0.0,
            kappa=round(kappa, 6),
            beta=round(beta, 6),
            theta_ols=round(theta_ols, 6),
            theta_se=0.01,
            residual_sigma=0.005,
            death_spiral_canary=False,
        )

    x_lag = spread_series[:-1]
    y_diff = [spread_series[i] - spread_series[i - 1] for i in range(1, n)]
    m = len(x_lag)

    mean_x = sum(x_lag) / m
    mean_y = sum(y_diff) / m

    s_xx = sum((x - mean_x) ** 2 for x in x_lag)
    s_xy = sum((x_lag[i] - mean_x) * (y_diff[i] - mean_y) for i in range(m))

    if s_xx < 1e-14:
        # Flat series: check if series is diverging away from 0 or stable at 0
        kappa = -0.05
    else:
        kappa = s_xy / s_xx

    alpha = mean_y - kappa * mean_x
    beta = 1.0 + kappa

    residuals = [y_diff[i] - (alpha + kappa * x_lag[i]) for i in range(m)]
    dof = max(1, m - 2)
    s2 = sum(r * r for r in residuals) / dof
    residual_sigma = math.sqrt(max(0.0, s2))
    se_kappa = math.sqrt(s2 / max(s_xx, 1e-12))

    # Death Spiral Canary: Veto S_t = 3 if beta = 1 + kappa >= 1.0 (PegGuard.pdf Page 5)
    if beta >= 1.0:
        return OLSFitResult(
            alpha=round(alpha, 6),
            kappa=round(kappa, 6),
            beta=round(beta, 6),
            theta_ols=0.0,
            theta_se=round(se_kappa / max(dt_hours, 1e-6), 6),
            residual_sigma=round(residual_sigma, 6),
            death_spiral_canary=True,
        )

    beta_pos = max(beta, 0.05)
    theta_ols = -math.log(beta_pos) / max(dt_hours, 1e-6)
    # Delta-method standard error: d(theta)/d(kappa) = -1 / ((1 + kappa) * dt)
    theta_se = se_kappa / (beta_pos * max(dt_hours, 1e-6))

    return OLSFitResult(
        alpha=round(alpha, 6),
        kappa=round(kappa, 6),
        beta=round(beta, 6),
        theta_ols=round(theta_ols, 6),
        theta_se=round(theta_se, 6),
        residual_sigma=round(residual_sigma, 6),
        death_spiral_canary=False,
    )


def estimate_layer2_regime(
    layer1: Layer1Result,
    spread_series: list[float] | None = None,
    dt_hours: float = 1.0,
    liquidity_stress: float = 0.25,
    redemption_paused: bool = False,
    p_insolvency_finbert: float = 0.05,
    tau_redeem_days: float = 1.0,
) -> Layer2Result:
    """Two-Stage Hybrid Estimator: Closed-Form AR(1) OLS + 3-Regime Markov-Switching SDE (PegGuard.pdf Page 5)."""
    if spread_series is None:
        # Synthesize a representative convergence trajectory ending at layer1.abnormal_spread_delta
        d = layer1.abnormal_spread_delta
        spread_series = [d * 0.6, d * 0.85, d * 1.10, d * 1.05, d * 0.96, d]

    ols = fit_ar1_ols(spread_series, dt_hours=dt_hours)
    abs_delta = abs(layer1.abnormal_spread_delta)
    abs_z = abs(layer1.z_score)

    # Evaluate Markov-Switching state likelihoods across S_t in {1, 2, 3}
    # Regime 3 (Fundamental Peg Collapse) triggers on:
    # - OLS Death Spiral Canary (beta >= 1.0)
    # - Severe Fundamental Fair Value impairment (fv_fund < 0.75)
    # - High FinBERT insolvency probability (p_insolvency >= 0.60)
    z_1 = 2.5 - 35.0 * abs_delta - 2.0 * liquidity_stress - 4.0 * (1.0 - layer1.reserve_ratio)
    z_2 = (
        -0.5
        + 25.0 * min(abs_delta, 0.15)
        + 2.5 * liquidity_stress
        + 1.5 * min(abs_z / 2.0, 2.5)
        - 5.0 * max(0.0, 0.80 - layer1.fv_fund)
    )
    z_3 = (
        -4.8
        + 18.0 * max(0.0, 1.0 - layer1.fv_fund)
        + 6.5 * p_insolvency_finbert
        + (5.5 if ols.death_spiral_canary else 0.0)
        + (3.0 if redemption_paused else 0.0)
        + 10.0 * max(0.0, abs_delta - 0.20)
    )

    max_z = max(z_1, z_2, z_3)
    w_1 = math.exp(z_1 - max_z)
    w_2 = math.exp(z_2 - max_z)
    w_3 = math.exp(z_3 - max_z)
    w_total = w_1 + w_2 + w_3

    p1 = w_1 / w_total
    p2 = w_2 / w_total
    p3 = w_3 / w_total

    # Hard Canary Override: if beta >= 1.0 or FV_fund < 0.50 or FinBERT insolvency >= 0.60 -> Regime 3
    if ols.death_spiral_canary or layer1.fv_fund < 0.50 or p_insolvency_finbert >= FINBERT_INSOLVENCY_VETO_THRESHOLD:
        regime = PegRegime.FUNDAMENTAL_PEG_COLLAPSE
        p3 = max(p3, 0.88)
        rem = 1.0 - p3
        p2 = rem * 0.80
        p1 = rem * 0.20
    elif p3 >= max(p1, p2):
        regime = PegRegime.FUNDAMENTAL_PEG_COLLAPSE
    elif p2 >= p1 or abs_delta >= 0.008:
        regime = PegRegime.TEMPORARY_LIQUIDITY_DISTRESS
    else:
        regime = PegRegime.NORMAL_MICROSTRUCTURE

    p_rec = max(0.0, min(1.0, p1 + p2))

    # Regime-specific SDE reversion speed theta(S_t) and half-life t_{1/2}(S_t) = ln(2) / theta(S_t)
    if regime == PegRegime.NORMAL_MICROSTRUCTURE:
        theta_active = max(ols.theta_ols, 0.25)  # rapid half-life (minutes to a few hours)
        half_life_h = math.log(2.0) / theta_active
        expected_duration_h = max(half_life_h * 2.0, 4.0)
        regime_name = "Regime 1 (Normal Microstructure)"
    elif regime == PegRegime.TEMPORARY_LIQUIDITY_DISTRESS:
        # In Regime 2, reversion slows to days (e.g. half-life ~18h-48h)
        theta_active = max(min(ols.theta_ols, 0.08), 0.020)
        half_life_h = math.log(2.0) / theta_active
        expected_duration_h = max(half_life_h * 1.5, tau_redeem_days * 24.0, 24.0)
        regime_name = "Regime 2 (Temporary Liquidity Distress)"
    else:
        theta_active = 0.0
        half_life_h = float("inf")
        expected_duration_h = float("inf")
        regime_name = "Regime 3 (Fundamental Peg Collapse)"

    death_spiral_veto = bool(regime == PegRegime.FUNDAMENTAL_PEG_COLLAPSE or ols.death_spiral_canary)

    return Layer2Result(
        regime=regime,
        regime_name=regime_name,
        p_regime_1_normal=round(p1, 4),
        p_regime_2_distress=round(p2, 4),
        p_regime_3_collapse=round(p3, 4),
        p_rec=round(p_rec, 4),
        ols=ols,
        theta_active=round(theta_active, 6),
        half_life_hours=round(half_life_h, 3) if math.isfinite(half_life_h) else float("inf"),
        expected_duration_hours=round(expected_duration_h, 3) if math.isfinite(expected_duration_h) else float("inf"),
        death_spiral_veto=death_spiral_veto,
    )


# =============================================================================
# Layer 3: Recovery-Risk EV & Signed Perpetual Funding Gate
# =============================================================================


class Layer3Input(BaseModel):
    """Inputs for Layer 3 Recovery-Risk EV & Signed Perpetual Funding Gate (PegGuard.pdf Page 5)."""

    funding_rate_8h: float = Field(
        0.0001,
        description="8-hour perpetual funding rate F_8h (+0.01% = +0.0001 contango rebate on short perp; <0 backwardation drag)",
    )
    borrow_apr: float = Field(0.02, ge=0, description="Annualized cross-margin / repo borrow interest rate")
    taker_fee: float = Field(0.0004, ge=0, description="Single-leg exchange/DEX taker fee (4 bps default)")
    order_size_usd: float = Field(10_000.0, gt=0, description="Order size Q in USD")
    l2_depth_usd: float = Field(2_000_000.0, gt=0, description="Current L2 order-book depth within 0.5% of mid-price")
    tau_redeem_days: float = Field(1.0, ge=0, description="Primary settlement / redemption queue delay in days")
    lgd: float = Field(0.15, ge=0, le=1.0, description="Loss Given Default (LGD) if peg fails permanently")
    hurdle_rate: float = Field(DEFAULT_HURDLE_RATE, ge=0, description="Minimum EV hurdle rate (+15 bps = 0.0015)")


class Layer3Result(BaseModel):
    """Outputs of Layer 3: Recovery-Risk EV & Signed Perpetual Funding Gate (PegGuard.pdf Page 5)."""

    abs_spread_delta: float = Field(description="|delta(t)| gross convergence spread")
    signed_funding_cf: float = Field(
        description="SignedFundingCF = +F_8h * [T_exp(S_t) / 8h] (Rebate if F_8h > 0; Cost Drag if F_8h < 0)"
    )
    borrow_cost: float = Field(description="BorrowCost(T_exp) over expected holding duration")
    double_taker_fee: float = Field(description="2 * TakerFee (entry + exit legs)")
    panic_slippage: float = Field(description="Slippage(Q, Depth_t, tau_redeem) under stressed order-book depth")
    net_gain_rec: float = Field(
        description="NetGain_rec = |delta(t)| + SignedFundingCF - BorrowCost - 2*TakerFee - Slippage"
    )
    expected_default_loss: float = Field(description="(1 - P_rec) * LGD")
    recovery_adjusted_ev: float = Field(description="Recovery-Adjusted EV = P_rec * NetGain_rec - (1 - P_rec) * LGD")
    recovery_adjusted_ev_bps: float = Field(description="Recovery-Adjusted EV in basis points")
    hurdle_rate_bps: float = Field(description="HurdleRate in basis points (+15.0 bps default)")
    passes_ev_gate: bool = Field(description="True iff S_t != 3 (beta < 1.0) AND Recovery-Adjusted EV >= HurdleRate")
    rejection_reason: str = ""


def compute_panic_slippage(order_size_usd: float, l2_depth_usd: float, tau_redeem_days: float) -> float:
    """Non-linear panic slippage model Slippage(Q, Depth_t, tau_redeem) (PegGuard.pdf Pages 5 & 9):
    Captures order-book depth depletion and T+3 redemption queue bottlenecks.
    """
    depth_ratio = order_size_usd / max(l2_depth_usd, 1.0)
    # Linear + quadratic depth impact (Avellaneda-Stoikov / square-root & convex order-book depletion)
    depth_slippage = 0.0003 + 0.015 * depth_ratio + 0.045 * (depth_ratio ** 1.5)
    # Redemption queue delay penalty (liquidity lockup amplification during T+3 bottlenecks)
    queue_multiplier = 1.0 + 0.08 * max(0.0, tau_redeem_days - 1.0)
    return min(0.50, depth_slippage * queue_multiplier)


def evaluate_layer3_ev(
    layer1: Layer1Result,
    layer2: Layer2Result,
    inp: Layer3Input,
) -> Layer3Result:
    """Executes Layer 3: Recovery-Risk EV & Signed Perpetual Funding Gate (PegGuard.pdf Page 5)."""
    abs_delta = abs(layer1.abnormal_spread_delta)

    if layer2.death_spiral_veto or not math.isfinite(layer2.expected_duration_hours):
        return Layer3Result(
            abs_spread_delta=round(abs_delta, 6),
            signed_funding_cf=0.0,
            borrow_cost=0.0,
            double_taker_fee=round(2.0 * inp.taker_fee, 6),
            panic_slippage=0.0,
            net_gain_rec=0.0,
            expected_default_loss=round((1.0 - layer2.p_rec) * inp.lgd, 6),
            recovery_adjusted_ev=round(-(1.0 - layer2.p_rec) * inp.lgd, 6),
            recovery_adjusted_ev_bps=round(-(1.0 - layer2.p_rec) * inp.lgd * 10_000.0, 2),
            hurdle_rate_bps=round(inp.hurdle_rate * 10_000.0, 2),
            passes_ev_gate=False,
            rejection_reason="Vetoed by Layer 2: Regime 3 Fundamental Peg Collapse / Death Spiral Canary (beta >= 1.0)",
        )

    t_exp_hours = layer2.expected_duration_hours
    # SignedFundingCF = +F_8h * [T_exp(S_t) / 8h]
    signed_funding_cf = inp.funding_rate_8h * (t_exp_hours / 8.0)

    # BorrowCost(T_exp)
    borrow_cost = inp.borrow_apr * (t_exp_hours / (365.0 * 24.0))

    double_taker = 2.0 * inp.taker_fee
    slippage = compute_panic_slippage(inp.order_size_usd, inp.l2_depth_usd, inp.tau_redeem_days)

    net_gain_rec = abs_delta + signed_funding_cf - borrow_cost - double_taker - slippage
    default_loss = (1.0 - layer2.p_rec) * inp.lgd
    ev = layer2.p_rec * net_gain_rec - default_loss

    passes = bool(
        layer2.regime != PegRegime.FUNDAMENTAL_PEG_COLLAPSE
        and not layer2.ols.death_spiral_canary
        and layer1.abnormal_spread_delta < 0.0  # asset must be trading at a discount below Baseline*(t)
        and ev >= inp.hurdle_rate
    )

    reason = ""
    if layer1.abnormal_spread_delta >= 0.0:
        reason = f"No discount below Baseline*(t): abnormal spread delta(t)={layer1.abnormal_spread_delta:+.4f} >= 0"
    elif not passes:
        reason = (
            f"Recovery-Adjusted EV ({ev * 10_000.0:+.1f} bps) below Execution Hurdle "
            f"(+{inp.hurdle_rate * 10_000.0:.1f} bps)"
        )

    return Layer3Result(
        abs_spread_delta=round(abs_delta, 6),
        signed_funding_cf=round(signed_funding_cf, 6),
        borrow_cost=round(borrow_cost, 6),
        double_taker_fee=round(double_taker, 6),
        panic_slippage=round(slippage, 6),
        net_gain_rec=round(net_gain_rec, 6),
        expected_default_loss=round(default_loss, 6),
        recovery_adjusted_ev=round(ev, 6),
        recovery_adjusted_ev_bps=round(ev * 10_000.0, 2),
        hurdle_rate_bps=round(inp.hurdle_rate * 10_000.0, 2),
        passes_ev_gate=passes,
        rejection_reason=reason,
    )


# =============================================================================
# Layer 4: Stateful Asset-Specific Token Check (FinBERT 50%, Microstructure 30%, Grok 20%)
# =============================================================================


class OnChainSpotMicrostructureInput(BaseModel):
    """The 4 on-chain & spot peg microstructure mechanisms (30% weight in Layer 4, PegGuard.pdf Page 6)."""

    # 1. Curve / DEX Pool Balance Tilt (e.g. Curve 3pool or stETH/ETH)
    curve_dumped_asset_share: float = Field(
        0.68, ge=0, le=1, description="Share of dumped asset in Curve pool (e.g., 0.78 = 78% tilted)"
    )
    curve_tilt_reversing: bool = Field(
        True, description="True if pool imbalance has peaked and is stabilizing/reversing; False if still accelerating"
    )

    # 2. DeFi Lending Utilization & Borrow APR Squeeze (Aave/Morpho)
    aave_utilization: float = Field(0.92, ge=0, le=1, description="Aave/Morpho lending pool utilization")
    aave_borrow_apr: float = Field(0.55, ge=0, description="Aave/Morpho variable borrow APR (e.g. 0.55 = 55% APR)")

    # 3. Primary Mint / Burn Redemption Velocity
    primary_redemption_burns_active: bool = Field(
        True, description="True if on-chain token burns are active during discount (institutional arb at $1.00 par)"
    )
    redemption_burn_velocity_score: float = Field(0.85, ge=0, le=1)

    # 4. Spot Order-Book Imbalance (OFI) & Bid-Wall Refill
    spot_ofi_bid_refill_score: float = Field(
        0.80, ge=0, le=1, description="Bid-to-ask depth recovery within 0.5% of mid-price"
    )


class Layer4Input(BaseModel):
    """Inputs for Layer 4 Stateful Asset-Specific Token Check (PegGuard.pdf Page 6)."""

    symbol: str = "USDC"
    last_check_ts: datetime | None = Field(
        None, description="Timestamp of previous inspection (defaults to 7-day lookback on initialization)"
    )
    now_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 1. Stateful FinBERT Sentinel (50% Weight + Hard Veto Gate)
    p_insolvency_finbert: float = Field(
        0.05, ge=0, le=1, description="Time-decayed FinBERT P(Insolvency) over delta window [t_last_check, t_now]"
    )
    finbert_solvency_score: float | None = Field(
        None, description="Optional explicit F_FinBERT in [0, 1]; defaults to 1.0 - p_insolvency_finbert"
    )

    # 2. On-Chain & Spot Peg Microstructure Matrix (30% Weight)
    microstructure: OnChainSpotMicrostructureInput = Field(default_factory=OnChainSpotMicrostructureInput)

    # 3. Grok API Dual-Persona Token Check (20% Weight)
    grok_retail_panic_index: int = Field(80, ge=0, le=100, description="Live X retail panic index (contrarian buy)")
    grok_retail_fomo_index: int = Field(15, ge=0, le=100, description="Live X retail FOMO index")
    grok_security_exploit_veto: bool = Field(
        False, description="True if PeckShield/Lookonchain flags active exploit or issuer freeze"
    )


class Layer4Result(BaseModel):
    """Outputs of Layer 4: Stateful Asset-Specific Token Check (PegGuard.pdf Page 6)."""

    symbol: str
    lookback_hours: float = Field(description="Delta window Dt = t_now - t_last_check in hours (default 168h = 7d)")
    i_safe_veto: int = Field(ge=0, le=1, description="Binary Hard Veto I_SafeVeto (0 if P(Insolvency) >= 0.60 or exploit)")
    f_finbert: float = Field(ge=0, le=1, description="FinBERT Solvency & Filing Sentinel Score F_FinBERT (50% weight)")
    m_onchain_spot: float = Field(
        ge=0, le=1, description="On-Chain & Spot Peg Microstructure Score M_OnChain+Spot (30% weight)"
    )
    g_grok: float = Field(ge=0, le=1, description="Grok Dual-Persona Token Score G_Grok (20% weight)")
    token_score_t: float = Field(
        ge=0,
        le=1,
        description="TokenScore T_t = I_SafeVeto * [0.50 * F_FinBERT + 0.30 * M_OnChain+Spot + 0.20 * G_Grok]",
    )
    microstructure_breakdown: dict[str, float]
    veto_reason: str = ""


def score_onchain_spot_microstructure(m: OnChainSpotMicrostructureInput, finbert_solvent: bool = True) -> tuple[float, dict[str, float]]:
    """Computes M_OnChain+Spot (30% Weight in Layer 4, PegGuard.pdf Page 6) across the 4 exact mechanisms:
    1. Curve / DEX Pool Balance Tilt
    2. DeFi Lending Utilization & Borrow APR Squeeze (Aave/Morpho)
    3. Primary Mint / Burn Redemption Velocity
    4. Spot Order-Book Imbalance (OFI) & Bid-Wall Refill
    """
    # 1. Curve Pool Tilt: wait while skew > 75% and accelerating; strong entry signal when peaking & reversing
    if m.curve_dumped_asset_share > 0.75 and not m.curve_tilt_reversing:
        curve_score = 0.15  # still accelerating into panic dump -> wait
    elif m.curve_tilt_reversing:
        curve_score = 0.90 if m.curve_dumped_asset_share >= 0.60 else 0.80
    else:
        curve_score = 0.55

    # 2. Aave/Morpho Utilization & Borrow APR Squeeze:
    # When utilization crosses kink (>90%) and borrow APR spikes (>50% APR) while FinBERT confirms solvency,
    # on-chain shorts are forced to buy back to repay debt -> strong short-squeeze catalyst!
    if finbert_solvent and m.aave_utilization >= 0.90 and m.aave_borrow_apr >= 0.50:
        aave_squeeze_score = 0.95
    elif finbert_solvent and m.aave_utilization >= 0.80:
        aave_squeeze_score = 0.75
    else:
        aave_squeeze_score = 0.55

    # 3. Primary Mint / Burn Redemption Velocity:
    burn_score = m.redemption_burn_velocity_score if m.primary_redemption_burns_active else 0.15

    # 4. Spot Order-Book Imbalance (OFI) & Bid-Wall Refill:
    ofi_score = m.spot_ofi_bid_refill_score

    composite = 0.25 * curve_score + 0.25 * aave_squeeze_score + 0.25 * burn_score + 0.25 * ofi_score
    breakdown = {
        "curve_pool_tilt_score": round(curve_score, 3),
        "aave_borrow_squeeze_score": round(aave_squeeze_score, 3),
        "primary_burn_velocity_score": round(burn_score, 3),
        "spot_ofi_bid_refill_score": round(ofi_score, 3),
    }
    return round(max(0.0, min(1.0, composite)), 4), breakdown


def evaluate_layer4_token_check(inp: Layer4Input) -> Layer4Result:
    """Executes Layer 4: Stateful Asset-Specific Token Check (PegGuard.pdf Page 6):
    TokenScore T_t = I_SafeVeto * [0.50 * F_FinBERT + 0.30 * M_OnChain+Spot + 0.20 * G_Grok]
    where I_SafeVeto = 0 if P(Insolvency | FinBERT) >= 0.60 or Grok flags an active exploit/freeze.
    """
    last_ts = inp.last_check_ts or (inp.now_ts - timedelta(days=7))
    lookback_hours = max(0.0, (inp.now_ts - last_ts).total_seconds() / 3600.0)

    f_finbert = (
        inp.finbert_solvency_score
        if inp.finbert_solvency_score is not None
        else max(0.0, min(1.0, 1.0 - inp.p_insolvency_finbert))
    )

    finbert_veto = inp.p_insolvency_finbert >= FINBERT_INSOLVENCY_VETO_THRESHOLD
    grok_veto = inp.grok_security_exploit_veto

    i_safe_veto = 0 if (finbert_veto or grok_veto) else 1
    veto_reason = ""
    if finbert_veto:
        veto_reason = (
            f"Layer 4 Binary Hard Veto (I_SafeVeto=0): P(Insolvency | FinBERT)={inp.p_insolvency_finbert:.2f} >= 0.60"
        )
    elif grok_veto:
        veto_reason = "Layer 4 Binary Hard Veto (I_SafeVeto=0): Grok security monitor flagged active exploit/issuer freeze"

    m_onchain_spot, m_breakdown = score_onchain_spot_microstructure(
        inp.microstructure, finbert_solvent=(i_safe_veto == 1)
    )

    if grok_veto:
        g_grok = 0.0
    else:
        diff = float(inp.grok_retail_panic_index - inp.grok_retail_fomo_index)
        g_grok = max(0.0, min(1.0, 0.5 + diff / 200.0))

    raw_blend = (
        LAYER4_FINBERT_WEIGHT * f_finbert
        + LAYER4_MICROSTRUCTURE_WEIGHT * m_onchain_spot
        + LAYER4_GROK_WEIGHT * g_grok
    )
    token_score_t = float(i_safe_veto) * raw_blend

    return Layer4Result(
        symbol=inp.symbol,
        lookback_hours=round(lookback_hours, 2),
        i_safe_veto=i_safe_veto,
        f_finbert=round(f_finbert, 4),
        m_onchain_spot=round(m_onchain_spot, 4),
        g_grok=round(g_grok, 4),
        token_score_t=round(max(0.0, min(1.0, token_score_t)), 4),
        microstructure_breakdown=m_breakdown,
        veto_reason=veto_reason,
    )


# =============================================================================
# Layer 5: Asset-Specific Hedging, FISCO BCOS Par-Capped Repo & Contagion Control
# =============================================================================


class FiscoParCappedRepoQuote(BaseModel):
    """FISCO BCOS Institutional Par-Capped USDT Repo Settlement quote (PegGuard.pdf Page 7):
    Effective Short Liability(t) = min[P_USDT(t), 1.000] * Q_borrowed
    - Eliminates >$1.00 retail short-squeeze risk (e.g. when USDT spikes to $1.04 during SVB flight-to-safety).
    - Captures asymmetric downside de-peg gain if shorted USDT drops below $1.00.
    """

    q_borrowed_usdt: float = Field(ge=0, description="Borrowed USDT quantity Q_borrowed")
    p_usdt_market: float = Field(gt=0, description="Current retail market price of USDT P_USDT(t)")
    par_cap: float = Field(1.000, description="Programmatic legal primary redemption par cap ($1.000)")
    effective_unit_liability: float = Field(description="min(P_USDT(t), 1.000)")
    effective_short_liability_usd: float = Field(description="min(P_USDT(t), 1.000) * Q_borrowed")
    naive_retail_perp_liability_usd: float = Field(description="P_USDT(t) * Q_borrowed on an un-capped retail exchange")
    squeeze_protection_saved_usd: float = Field(
        description="Artificial short-squeeze loss avoided vs naive retail perp when P_USDT(t) > 1.000"
    )
    downside_depeg_gain_usd: float = Field(
        description="Asymmetric hedge gain captured when P_USDT(t) < 1.000"
    )


def compute_fisco_par_capped_repo(q_borrowed_usdt: float, p_usdt_market: float = 1.000) -> FiscoParCappedRepoQuote:
    """Computes the exact FISCO BCOS Par-Capped USDT Repo liability (PegGuard.pdf Page 7):
    Effective Short Liability(t) = min[P_USDT(t), 1.000] * Q_borrowed
    """
    unit_liability = min(p_usdt_market, 1.000)
    effective_liability = unit_liability * q_borrowed_usdt
    naive_liability = p_usdt_market * q_borrowed_usdt
    squeeze_saved = max(0.0, (p_usdt_market - 1.000) * q_borrowed_usdt)
    downside_gain = max(0.0, (1.000 - p_usdt_market) * q_borrowed_usdt)

    return FiscoParCappedRepoQuote(
        q_borrowed_usdt=round(q_borrowed_usdt, 4),
        p_usdt_market=round(p_usdt_market, 6),
        par_cap=1.000,
        effective_unit_liability=round(unit_liability, 6),
        effective_short_liability_usd=round(effective_liability, 4),
        naive_retail_perp_liability_usd=round(naive_liability, 4),
        squeeze_protection_saved_usd=round(squeeze_saved, 4),
        downside_depeg_gain_usd=round(downside_gain, 4),
    )


class Layer5Input(BaseModel):
    """Inputs for Layer 5 Asset-Specific Hedging & Contagion Position Sizing (PegGuard.pdf Page 7)."""

    symbol: str = "USDC"
    base_size_usd: float = Field(10_000.0, ge=0, description="BaseSize capital allocation in USD")
    max_order_cap_usd: float | None = Field(None, description="Optional mandate / tether radius cap in USD")
    alpha_convexity: float = Field(0.25, ge=0, description="Convexity scaling parameter alpha")
    z_threshold: float = Field(1.5, ge=0, description="Dislocation Z-score threshold for convex scaling")
    p_usdt_market: float = Field(1.000, gt=0, description="Current market price of USDT P_USDT(t) for Class B Repo")
    peer_distress_probs: dict[str, float] = Field(
        default_factory=dict,
        description="Map of correlated asset j -> DistressProb_j (Regime 2 + Regime 3 probability)",
    )
    contagion_matrix: dict[str, dict[str, float]] = Field(default_factory=lambda: DEFAULT_CONTAGION_MATRIX)


class Layer5Result(BaseModel):
    """Outputs of Layer 5: Asset-Specific Hedging & Contagion Control (PegGuard.pdf Page 7)."""

    symbol: str
    hedge_class: HedgeClass
    long_leg_venue: str
    long_leg_instrument: str
    short_leg_venue: str
    short_leg_instrument: str
    convex_z_multiplier: float = Field(description="1 + alpha * max(0, |Z_i| - Threshold)^2")
    contagion_penalty_sum: float = Field(description="sum_{j != i} beta_{ij} * DistressProb_j")
    contagion_brake_factor: float = Field(description="max(0, 1 - sum_{j != i} beta_{ij} * DistressProb_j)")
    raw_order_size_usd: float = Field(
        description="BaseSize * [1 + alpha * (|Z_i| - Threshold)^2] * T_{i,t} * max(0, 1 - sum beta_ij * DistressProb_j)"
    )
    final_order_size_usd: float = Field(description="Final order size after mandate/tether cap")
    fisco_repo_quote: FiscoParCappedRepoQuote | None = Field(
        None, description="Populated for Class B Fiat-Pegged Stablecoins hedged via FISCO BCOS Par-Capped USDT Repo"
    )


def evaluate_layer5_hedge_and_sizing(
    layer1: Layer1Result,
    layer4: Layer4Result,
    inp: Layer5Input,
) -> Layer5Result:
    """Executes Layer 5: Asset-Specific Hedging & Contagion Control (PegGuard.pdf Page 7):
    OrderSize_i = BaseSize * [1 + alpha * (|Z_i| - Threshold)^2] * T_{i,t} * max[0, 1 - sum_{j != i} beta_{ij} * DistressProb_j]
    """
    symbol = inp.symbol
    abs_z = abs(layer1.z_score)
    excess_z = max(0.0, abs_z - inp.z_threshold)
    convex_mult = 1.0 + inp.alpha_convexity * (excess_z ** 2)

    betas = inp.contagion_matrix.get(symbol, {})
    contagion_sum = sum(
        beta_ij * max(0.0, min(1.0, inp.peer_distress_probs.get(peer, 0.0)))
        for peer, beta_ij in betas.items()
        if peer != symbol
    )
    contagion_brake = max(0.0, 1.0 - contagion_sum)

    raw_size = inp.base_size_usd * convex_mult * layer4.token_score_t * contagion_brake
    if layer4.i_safe_veto == 0 or layer1.abnormal_spread_delta >= 0.0:
        raw_size = 0.0

    final_size = min(raw_size, inp.max_order_cap_usd) if inp.max_order_cap_usd is not None else raw_size

    # Asset-Specific Hedge Selection (Class A vs Class B)
    if symbol in CRYPTO_PEGGED_ASSETS:
        hedge_class: HedgeClass = "CLASS_A_CRYPTO_PERP"
        long_venue = "ethereum_curve_steth_pool" if symbol == "stETH" else "ethereum_spot_dex"
        long_inst = f"LONG_SPOT_{symbol}"
        short_venue = "perpetual_exchange_eth_perp"
        short_inst = "SHORT_ETH_PERP"
        repo_quote = None
    else:
        hedge_class = "CLASS_B_FISCO_PAR_REPO"
        long_venue = "ethereum_curve_3pool"
        long_inst = f"LONG_SPOT_{symbol}"
        short_venue = "fisco_bcos_par_capped_repo_facility"
        short_inst = "FISCO_BCOS_PAR_CAPPED_USDT_REPO"
        repo_quote = compute_fisco_par_capped_repo(q_borrowed_usdt=final_size, p_usdt_market=inp.p_usdt_market)

    return Layer5Result(
        symbol=symbol,
        hedge_class=hedge_class,
        long_leg_venue=long_venue,
        long_leg_instrument=long_inst,
        short_leg_venue=short_venue,
        short_leg_instrument=short_inst,
        convex_z_multiplier=round(convex_mult, 4),
        contagion_penalty_sum=round(contagion_sum, 4),
        contagion_brake_factor=round(contagion_brake, 4),
        raw_order_size_usd=round(raw_size, 2),
        final_order_size_usd=round(final_size, 2),
        fisco_repo_quote=repo_quote,
    )


# =============================================================================
# Master 5-Layer PegGuard Pipeline & Evaluation Report
# =============================================================================


class PegGuardMarketInput(BaseModel):
    """Unified input packet for evaluating a pegged/staked asset through all 5 PegGuard layers."""

    symbol: str = "USDC"
    layer1: Layer1Input = Field(default_factory=Layer1Input)
    spread_series: list[float] | None = None
    dt_hours: float = 1.0
    liquidity_stress: float = Field(0.25, ge=0, le=1)
    redemption_paused: bool = False
    layer3: Layer3Input = Field(default_factory=Layer3Input)
    layer4: Layer4Input = Field(default_factory=Layer4Input)
    layer5: Layer5Input = Field(default_factory=Layer5Input)


class PegGuardDecision(BaseModel):
    """Complete 5-Layer PegGuard evaluation output."""

    symbol: str
    authorized: bool = Field(description="True iff all 5 PegGuard gates authorize two-leg arbitrage execution")
    rejection_reasons: list[str] = Field(default_factory=list)
    layer1: Layer1Result
    layer2: Layer2Result
    layer3: Layer3Result
    layer4: Layer4Result
    layer5: Layer5Result
    summary: str


class PegGuardEngine:
    """Executes all 5 sequential layers of the PegGuard Framework (PegGuard.pdf Pages 3-9)."""

    def evaluate(self, market_input: PegGuardMarketInput) -> PegGuardDecision:
        symbol = market_input.symbol
        l1_in = market_input.layer1.model_copy(update={"symbol": symbol})
        l4_in = market_input.layer4.model_copy(update={"symbol": symbol})
        l5_in = market_input.layer5.model_copy(update={"symbol": symbol})

        # Layer 1: Dual-Anchor Fair-Value & Multi-Horizon Equilibrium Calibration
        l1 = calibrate_layer1(l1_in)

        # Layer 4 (run before/with Layer 2 so FinBERT insolvency feeds the Regime 3 canary too)
        l4 = evaluate_layer4_token_check(l4_in)

        # Layer 2: 3-Regime Markov-Switching Duration & Fast OLS Fallback
        l2 = estimate_layer2_regime(
            layer1=l1,
            spread_series=market_input.spread_series,
            dt_hours=market_input.dt_hours,
            liquidity_stress=market_input.liquidity_stress,
            redemption_paused=market_input.redemption_paused,
            p_insolvency_finbert=l4_in.p_insolvency_finbert,
            tau_redeem_days=l1_in.tau_redeem_days,
        )

        # Layer 3: Recovery-Risk EV & Signed Perpetual Funding Gate
        l3 = evaluate_layer3_ev(layer1=l1, layer2=l2, inp=market_input.layer3)

        # Layer 5: Asset-Specific Hedging, FISCO BCOS Par-Capped Repo & Contagion Sizing
        l5 = evaluate_layer5_hedge_and_sizing(layer1=l1, layer4=l4, inp=l5_in)

        reasons: list[str] = []
        if l1.abnormal_spread_delta >= 0.0:
            reasons.append(f"Layer 1: Asset is not trading below Baseline*(t) (delta={l1.abnormal_spread_delta:+.4f})")
        if l2.death_spiral_veto or l2.regime == PegRegime.FUNDAMENTAL_PEG_COLLAPSE:
            reasons.append(
                f"Layer 2: {l2.regime_name} vetoed trade (beta={l2.ols.beta:.3f}, FV_fund={l1.fv_fund:.3f})"
            )
        if not l3.passes_ev_gate and l3.rejection_reason:
            reasons.append(f"Layer 3: {l3.rejection_reason}")
        if l4.i_safe_veto == 0:
            reasons.append(l4.veto_reason or "Layer 4: Binary Hard Veto (I_SafeVeto=0)")
        elif l4.token_score_t < 0.25:
            reasons.append(f"Layer 4: TokenScore T_t ({l4.token_score_t:.3f}) below minimum conviction threshold (0.25)")
        if l5.final_order_size_usd <= 0.0:
            reasons.append("Layer 5: Contagion brake or zero sizing reduced OrderSize to $0.00")

        authorized = len(reasons) == 0

        if authorized:
            summary = (
                f"PegGuard AUTHORIZED {symbol} ({l5.hedge_class}): "
                f"R_cons={l1.r_cons:.4f} vs Baseline*={l1.baseline_star:.4f} (delta={l1.abnormal_spread_delta:+.4f}, Z={l1.z_score:+.2f}), "
                f"{l2.regime_name} (P_rec={l2.p_rec:.1%}, t_1/2={l2.half_life_hours:.1f}h), "
                f"EV={l3.recovery_adjusted_ev_bps:+.1f} bps (>= +{l3.hurdle_rate_bps:.1f} bps), "
                f"TokenScore T_t={l4.token_score_t:.3f}, "
                f"OrderSize=${l5.final_order_size_usd:,.2f} via [{l5.long_leg_instrument} + {l5.short_leg_instrument}]"
            )
        else:
            summary = f"PegGuard ABSTAINED/VETOED {symbol}: " + " | ".join(reasons)

        return PegGuardDecision(
            symbol=symbol,
            authorized=authorized,
            rejection_reasons=reasons,
            layer1=l1,
            layer2=l2,
            layer3=l3,
            layer4=l4,
            layer5=l5,
            summary=summary,
        )


# =============================================================================
# Canonical Historical Crisis Scenarios (PegGuard.pdf Page 9 Table)
# =============================================================================


def crisis_scenario_svb_usdc(
    order_size_usd: float = 500.0,
    peer_distress_probs: dict[str, float] | None = None,
) -> PegGuardMarketInput:
    """Episode 1 (March 2023): SVB Collapse & Multi-Coin Contagion (USDC / USDT).
    - USDC dropped to $0.88; Curve 3pool tilted >80% USDC/DAI (now peaking & reversing);
    - Retail USDT spiked to $1.04 during flight-to-safety;
    - Reserves remained 92%+ liquid T-bills + Fed backstop; FinBERT separates liquidity delay from insolvency.
    """
    return PegGuardMarketInput(
        symbol="USDC",
        layer1=Layer1Input(
            symbol="USDC",
            p_par=1.000,
            liquid_reserves=0.985,
            circulating_supply=1.000,
            y_asset=0.0,
            r_fee=0.001,
            c_illiquidity=0.002,
            tau_redeem_days=2.0,
            r_direct=0.880,
            p_pegged_usdt=0.915,
            p_anchor_usdt=1.040,  # retail USDT spiked to $1.04!
            w_dir=0.60,
            avg_1w=0.995,
            avg_1m=0.999,
            avg_1y=1.000,
            sigma_30d=0.025,
        ),
        spread_series=[-0.04, -0.08, -0.13, -0.125, -0.118, -0.105],
        dt_hours=1.0,
        liquidity_stress=0.65,
        redemption_paused=False,
        layer3=Layer3Input(
            funding_rate_8h=0.0002,
            borrow_apr=0.03,
            taker_fee=0.0004,
            order_size_usd=order_size_usd,
            l2_depth_usd=2_500_000.0,
            tau_redeem_days=2.0,
            lgd=0.08,
            hurdle_rate=DEFAULT_HURDLE_RATE,
        ),
        layer4=Layer4Input(
            symbol="USDC",
            p_insolvency_finbert=0.12,  # FinBERT identifies temporary SVB wire delay, not structural insolvency
            microstructure=OnChainSpotMicrostructureInput(
                curve_dumped_asset_share=0.78,
                curve_tilt_reversing=True,
                aave_utilization=0.94,
                aave_borrow_apr=0.62,
                primary_redemption_burns_active=True,
                redemption_burn_velocity_score=0.90,
                spot_ofi_bid_refill_score=0.85,
            ),
            grok_retail_panic_index=92,
            grok_retail_fomo_index=8,
            grok_security_exploit_veto=False,
        ),
        layer5=Layer5Input(
            symbol="USDC",
            base_size_usd=order_size_usd,
            max_order_cap_usd=order_size_usd,
            alpha_convexity=0.25,
            z_threshold=1.5,
            p_usdt_market=1.040,  # Retail USDT spiked to $1.04 -> FISCO BCOS Par-Capped Repo caps liability at $1.000!
            peer_distress_probs=peer_distress_probs or {},
        ),
    )


def crisis_scenario_terra_ust(order_size_usd: float = 500.0) -> PegGuardMarketInput:
    """Episode 2 (May 2022): Terra / UST Terminal Collapse.
    - Mint-burn death spiral; FV_fund collapsed toward $0.00 while 30-day moving average remained near $1.00;
    - Autoregressive persistence beta >= 1.0 (non-stationary divergence);
    - FinBERT detects structural insolvency (P(Insolvency) >= 0.60 -> I_SafeVeto = 0).
    """
    return PegGuardMarketInput(
        symbol="UST",
        layer1=Layer1Input(
            symbol="UST",
            p_par=1.000,
            liquid_reserves=0.08,  # reserves depleted in LFG death spiral
            circulating_supply=1.000,
            y_asset=0.0,
            r_fee=0.01,
            c_illiquidity=0.15,
            tau_redeem_days=7.0,
            r_direct=0.650,
            p_pegged_usdt=0.650,
            p_anchor_usdt=1.000,
            w_dir=0.60,
            avg_1w=0.960,
            avg_1m=0.992,
            avg_1y=0.999,
            sigma_30d=0.040,
        ),
        # Non-stationary diverging spread (beta >= 1.0)
        spread_series=[-0.02, -0.05, -0.11, -0.22, -0.35, -0.55],
        dt_hours=1.0,
        liquidity_stress=0.98,
        redemption_paused=True,
        layer3=Layer3Input(
            funding_rate_8h=-0.0050,  # extreme backwardation
            borrow_apr=0.45,
            taker_fee=0.0010,
            order_size_usd=order_size_usd,
            l2_depth_usd=150_000.0,
            tau_redeem_days=7.0,
            lgd=0.95,
            hurdle_rate=DEFAULT_HURDLE_RATE,
        ),
        layer4=Layer4Input(
            symbol="UST",
            p_insolvency_finbert=0.92,  # >= 0.60 -> Binary Hard Veto I_SafeVeto = 0!
            microstructure=OnChainSpotMicrostructureInput(
                curve_dumped_asset_share=0.96,
                curve_tilt_reversing=False,
                aave_utilization=0.99,
                aave_borrow_apr=1.20,
                primary_redemption_burns_active=False,
                redemption_burn_velocity_score=0.05,
                spot_ofi_bid_refill_score=0.05,
            ),
            grok_retail_panic_index=98,
            grok_retail_fomo_index=2,
            grok_security_exploit_veto=True,
        ),
        layer5=Layer5Input(
            symbol="UST",
            base_size_usd=order_size_usd,
            max_order_cap_usd=order_size_usd,
            p_usdt_market=1.000,
        ),
    )


def crisis_scenario_steth_3ac(order_size_usd: float = 500.0) -> PegGuardMarketInput:
    """Episode 3 (June 2022): stETH Liquidity Crisis (stETH / ETH).
    - 7% discount (0.93 ETH) from 3AC forced liquidations & Curve stETH pool skew;
    - Beacon ETH reserves remained 100% solvent (FV_fund ~ 1.0);
    - FinBERT (50% weight) confirms zero protocol insolvency;
    - Class A Hedge: Long Spot (stETH) + Short Reference Perpetual (ETH-PERP) harvests spread safely.
    """
    return PegGuardMarketInput(
        symbol="stETH",
        layer1=Layer1Input(
            symbol="stETH",
            p_par=1.000,
            liquid_reserves=1.000,  # 100% 1:1 Beacon Chain ETH backing
            circulating_supply=1.000,
            y_asset=0.042,  # +4.2% Ethereum staking APR
            r_fee=0.000,
            c_illiquidity=0.003,
            tau_redeem_days=3.0,
            r_direct=0.930,  # 7% discount on stETH/ETH
            p_pegged_usdt=1116.0,
            p_anchor_usdt=1200.0,  # 1116 / 1200 = 0.930
            w_dir=0.60,
            avg_1w=0.975,
            avg_1m=0.988,
            avg_1y=0.996,
            sigma_30d=0.018,
        ),
        spread_series=[-0.03, -0.05, -0.075, -0.072, -0.068, -0.059],
        dt_hours=1.0,
        liquidity_stress=0.55,
        redemption_paused=False,
        layer3=Layer3Input(
            funding_rate_8h=0.00015,  # Positive contango funding -> Short ETH-PERP earns funding rebate!
            borrow_apr=0.015,
            taker_fee=0.0004,
            order_size_usd=order_size_usd,
            l2_depth_usd=5_000_000.0,
            tau_redeem_days=3.0,
            lgd=0.05,
            hurdle_rate=DEFAULT_HURDLE_RATE,
        ),
        layer4=Layer4Input(
            symbol="stETH",
            p_insolvency_finbert=0.06,  # FinBERT confirms Beacon Chain ETH reserves are 100% solvent
            microstructure=OnChainSpotMicrostructureInput(
                curve_dumped_asset_share=0.76,
                curve_tilt_reversing=True,  # Curve stETH/ETH pool tilt stabilizing after 3AC liquidation wave
                aave_utilization=0.85,
                aave_borrow_apr=0.18,
                primary_redemption_burns_active=True,
                redemption_burn_velocity_score=0.85,
                spot_ofi_bid_refill_score=0.88,
            ),
            grok_retail_panic_index=85,
            grok_retail_fomo_index=10,
            grok_security_exploit_veto=False,
        ),
        layer5=Layer5Input(
            symbol="stETH",
            base_size_usd=order_size_usd,
            max_order_cap_usd=order_size_usd,
            alpha_convexity=0.25,
            z_threshold=1.5,
        ),
    )


def default_pegguard_input_for_symbol(symbol: str, order_size_usd: float = 250.0) -> PegGuardMarketInput:
    """Returns a realistic default PegGuardMarketInput for a given symbol when invoked by PegGuardArbitrageExecutor."""
    norm = symbol.strip()
    if norm.upper() == "UST":
        return crisis_scenario_terra_ust(order_size_usd=order_size_usd)
    if norm in CRYPTO_PEGGED_ASSETS or norm.lower() in ("steth", "wbeth", "reth", "ezeth"):
        canonical = "stETH" if norm.lower() == "steth" else norm
        inp = crisis_scenario_steth_3ac(order_size_usd=order_size_usd)
        return inp.model_copy(update={"symbol": canonical})
    inp = crisis_scenario_svb_usdc(order_size_usd=order_size_usd)
    return inp.model_copy(update={"symbol": norm.upper()})

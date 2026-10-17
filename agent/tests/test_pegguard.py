"""Comprehensive tests for the 5-Layer PegGuard Framework and PegGuardArbitrageExecutor (PegGuard.pdf)."""

from __future__ import annotations

import math

from tecc_brain.models import ActionType, CardLabel, ExecutionIntent, usd_to_onchain
from tecc_brain.onchain.executor import MarketRouter, PegGuardArbitrageExecutor
from tecc_brain.pegguard import (
    DEFAULT_HURDLE_RATE,
    Layer1Input,
    Layer3Input,
    Layer4Input,
    Layer5Input,
    OnChainSpotMicrostructureInput,
    PegGuardEngine,
    PegGuardMarketInput,
    PegRegime,
    calibrate_layer1,
    compute_fisco_par_capped_repo,
    compute_fundamental_fair_value,
    compute_panic_slippage,
    crisis_scenario_steth_3ac,
    crisis_scenario_svb_usdc,
    crisis_scenario_terra_ust,
    estimate_layer2_regime,
    evaluate_layer3_ev,
    evaluate_layer4_token_check,
    evaluate_layer5_hedge_and_sizing,
    fit_ar1_ols,
)


def _arb_intent(venue_id: str, asset_in: str, usd: float = 400.0) -> ExecutionIntent:
    return ExecutionIntent(
        card_label=CardLabel.OPPORTUNITY,
        venue_id=venue_id,
        action=ActionType.BUY_DISCOUNT,
        asset_in=asset_in,
        amount_usd=usd,
        amount_onchain=usd_to_onchain(usd),
        market="arbitrage",
    )


# =============================================================================
# Layer 1: Dual-Anchor Fair-Value & Multi-Horizon Equilibrium Calibration
# =============================================================================


def test_layer1_fundamental_fair_value_and_conservative_baseline():
    """Verifies Layer 1 formulas (PegGuard.pdf Page 4):
    - FV_fund(t) = P_par * min(1, LiquidReserves / CirculatingSupply) * exp[(y_asset - r_fee - c_illiquidity) * tau_redeem]
    - R_cons(t) = w_dir * R_direct(t) + (1 - w_dir) * [P_pegged/USDT(t) / P_anchor/USDT(t)]
    - mu_mkt(t) = w_1w * Avg_1w + w_1m * Avg_1m + w_1y * Avg_1y
    - Baseline*(t) = min(FV_fund(t), mu_mkt(t))
    - delta(t) = R_cons(t) - Baseline*(t), Z(t) = delta(t) / sigma_30D(t)
    """
    # Case 1: Persistent market discount (mu_mkt = 0.98) while FV_fund = 1.00 -> Baseline*(t) = 0.98 (avoids dead trades)
    l1_mkt_disc = calibrate_layer1(
        Layer1Input(
            symbol="USDC",
            p_par=1.0,
            liquid_reserves=1.0,
            circulating_supply=1.0,
            y_asset=0.0,
            r_fee=0.0,
            c_illiquidity=0.0,
            tau_redeem_days=0.0,
            r_direct=0.98,
            p_pegged_usdt=0.98,
            p_anchor_usdt=1.00,
            w_dir=0.60,
            avg_1w=0.98,
            avg_1m=0.98,
            avg_1y=0.98,
            sigma_30d=0.01,
        )
    )
    assert math.isclose(l1_mkt_disc.fv_fund, 1.0, abs_tol=1e-6)
    assert math.isclose(l1_mkt_disc.mu_mkt, 0.98, abs_tol=1e-6)
    assert math.isclose(l1_mkt_disc.baseline_star, 0.98, abs_tol=1e-6)
    assert math.isclose(l1_mkt_disc.abnormal_spread_delta, 0.0, abs_tol=1e-6)

    # Case 2: Reserve impairment drops FV_fund to ~0.82 today while moving averages sit at 1.00 -> Baseline*(t) drops to 0.82!
    l1_impair = calibrate_layer1(
        Layer1Input(
            symbol="UST",
            p_par=1.0,
            liquid_reserves=0.82,
            circulating_supply=1.0,
            y_asset=0.0,
            r_fee=0.0,
            c_illiquidity=0.0,
            tau_redeem_days=0.0,
            r_direct=0.85,
            p_pegged_usdt=0.85,
            p_anchor_usdt=1.00,
            w_dir=0.60,
            avg_1w=1.00,
            avg_1m=1.00,
            avg_1y=1.00,
            sigma_30d=0.02,
        )
    )
    assert math.isclose(l1_impair.fv_fund, 0.82, abs_tol=1e-6)
    assert math.isclose(l1_impair.mu_mkt, 1.00, abs_tol=1e-6)
    assert math.isclose(l1_impair.baseline_star, 0.82, abs_tol=1e-6)
    # R_cons (0.85) > Baseline* (0.82) -> positive abnormal spread (+0.03), so no discount buy!
    assert l1_impair.abnormal_spread_delta > 0.0


# =============================================================================
# Layer 2: 3-Regime Markov-Switching Duration & Fast OLS Fallback
# =============================================================================


def test_layer2_closed_form_ar1_ols_and_death_spiral_canary():
    """Verifies Layer 2 Closed-Form AR(1) OLS Engine and Death Spiral Canary (PegGuard.pdf Page 5):
    - Stationary mean-reverting series -> kappa < 0, beta < 1.0, theta_OLS = -ln(1 + kappa)/dt > 0, canary = False
    - Diverging non-stationary series -> kappa >= 0, beta >= 1.0, canary = True -> Regime 3 Veto
    """
    # Stationary converging spread series
    ols_rev = fit_ar1_ols([-0.10, -0.08, -0.064, -0.0512, -0.041, -0.0328], dt_hours=1.0)
    assert ols_rev.kappa < 0.0
    assert ols_rev.beta < 1.0
    assert ols_rev.theta_ols > 0.0
    assert ols_rev.death_spiral_canary is False

    # Diverging death-spiral series (beta >= 1.0)
    ols_div = fit_ar1_ols([-0.02, -0.05, -0.11, -0.23, -0.45, -0.80], dt_hours=1.0)
    assert ols_div.beta >= 1.0
    assert ols_div.death_spiral_canary is True


# =============================================================================
# Layer 3: Recovery-Risk EV & Signed Perpetual Funding Gate
# =============================================================================


def test_layer3_signed_perpetual_funding_rebate_vs_backwardation_drag():
    """Verifies Layer 3 Signed Perpetual Funding Cashflow and +15 bps Execution Hurdle Rule (PegGuard.pdf Page 5):
    - When F_8h > 0 (contango), short perp hedge earns a positive funding rebate (+SignedFundingCF).
    - When F_8h << 0 (deep backwardation) or high LGD erodes EV below +15 bps, the gate rejects the trade.
    """
    l1 = calibrate_layer1(crisis_scenario_steth_3ac().layer1)
    l2 = estimate_layer2_regime(l1, spread_series=[-0.04, -0.07, -0.068, -0.060, -0.055], p_insolvency_finbert=0.05)
    assert l2.regime == PegRegime.TEMPORARY_LIQUIDITY_DISTRESS

    # 1. Contango (F_8h = +0.03% per 8h) -> positive funding rebate
    l3_contango = evaluate_layer3_ev(
        l1,
        l2,
        Layer3Input(
            funding_rate_8h=0.0003,
            borrow_apr=0.01,
            taker_fee=0.0004,
            order_size_usd=10_000.0,
            l2_depth_usd=5_000_000.0,
            tau_redeem_days=2.0,
            lgd=0.05,
            hurdle_rate=DEFAULT_HURDLE_RATE,
        ),
    )
    assert l3_contango.signed_funding_cf > 0.0
    assert l3_contango.passes_ev_gate is True
    assert l3_contango.recovery_adjusted_ev_bps >= 15.0

    # 2. Severe backwardation (F_8h = -1.5% per 8h) -> negative drag erodes EV below +15 bps hurdle
    l3_backwardation = evaluate_layer3_ev(
        l1,
        l2,
        Layer3Input(
            funding_rate_8h=-0.015,
            borrow_apr=0.25,
            taker_fee=0.001,
            order_size_usd=100_000.0,
            l2_depth_usd=200_000.0,
            tau_redeem_days=3.0,
            lgd=0.25,
            hurdle_rate=DEFAULT_HURDLE_RATE,
        ),
    )
    assert l3_backwardation.signed_funding_cf < 0.0
    assert l3_backwardation.passes_ev_gate is False


# =============================================================================
# Layer 4: Stateful Asset-Specific Token Check (50% FinBERT, 30% On-Chain, 20% Grok)
# =============================================================================


def test_layer4_token_check_weights_and_binary_hard_veto():
    """Verifies Layer 4 Token Check formula (PegGuard.pdf Page 6):
    TokenScore T_t = I_SafeVeto * [0.50 * F_FinBERT + 0.30 * M_OnChain+Spot + 0.20 * G_Grok]
    where I_SafeVeto = 0 if P(Insolvency | FinBERT) >= 0.60 or Grok flags active exploit.
    """
    # 1. Solvent asset with Aave borrow squeeze + Curve pool reversal + retail panic
    res_safe = evaluate_layer4_token_check(
        Layer4Input(
            symbol="USDC",
            p_insolvency_finbert=0.10,  # F_FinBERT = 0.90
            microstructure=OnChainSpotMicrostructureInput(
                curve_dumped_asset_share=0.78,
                curve_tilt_reversing=True,
                aave_utilization=0.95,
                aave_borrow_apr=0.65,
                primary_redemption_burns_active=True,
                redemption_burn_velocity_score=0.90,
                spot_ofi_bid_refill_score=0.85,
            ),
            grok_retail_panic_index=90,
            grok_retail_fomo_index=10,
            grok_security_exploit_veto=False,
        )
    )
    assert res_safe.i_safe_veto == 1
    assert res_safe.f_finbert == 0.90
    expected_t = 0.50 * res_safe.f_finbert + 0.30 * res_safe.m_onchain_spot + 0.20 * res_safe.g_grok
    assert math.isclose(res_safe.token_score_t, expected_t, abs_tol=1e-3)
    assert res_safe.token_score_t > 0.80

    # 2. Binary Hard Veto when P(Insolvency | FinBERT) >= 0.60
    res_veto = evaluate_layer4_token_check(
        Layer4Input(
            symbol="UST",
            p_insolvency_finbert=0.65,  # >= 0.60 -> I_SafeVeto = 0
            grok_retail_panic_index=95,
            grok_retail_fomo_index=5,
        )
    )
    assert res_veto.i_safe_veto == 0
    assert res_veto.token_score_t == 0.0
    assert "I_SafeVeto=0" in res_veto.veto_reason


# =============================================================================
# Layer 5: FISCO BCOS Par-Capped USDT Repo & Contagion Matrix
# =============================================================================


def test_layer5_fisco_bcos_par_capped_repo_and_contagion_brake():
    """Verifies Layer 5 FISCO BCOS Par-Capped USDT Repo & Contagion Matrix (PegGuard.pdf Page 7):
    - Effective Short Liability(t) = min[P_USDT(t), 1.000] * Q_borrowed
      * When P_USDT spikes to $1.04, liability stays capped at $1.000 * Q_borrowed (saves $0.04 * Q_borrowed squeeze loss).
      * When P_USDT drops to $0.95, liability shrinks to $0.950 * Q_borrowed (captures $0.05 * Q_borrowed downside gain).
    - Portfolio Contagion Brake scales down DAI/FRAX allocation when USDC is in distress.
    """
    # 1. Retail USDT short-squeeze at $1.04
    quote_squeeze = compute_fisco_par_capped_repo(q_borrowed_usdt=10_000.0, p_usdt_market=1.040)
    assert quote_squeeze.effective_unit_liability == 1.000
    assert quote_squeeze.effective_short_liability_usd == 10_000.0
    assert quote_squeeze.naive_retail_perp_liability_usd == 10_400.0
    assert math.isclose(quote_squeeze.squeeze_protection_saved_usd, 400.0, abs_tol=1e-4)

    # 2. Asymmetric downside convexity when USDT de-pegs to $0.94
    quote_depeg = compute_fisco_par_capped_repo(q_borrowed_usdt=10_000.0, p_usdt_market=0.940)
    assert quote_depeg.effective_unit_liability == 0.940
    assert quote_depeg.effective_short_liability_usd == 9_400.0
    assert math.isclose(quote_depeg.downside_depeg_gain_usd, 600.0, abs_tol=1e-4)

    # 3. Contagion Brake on DAI when USDC + FRAX are in distress
    l1 = calibrate_layer1(crisis_scenario_svb_usdc().layer1.model_copy(update={"symbol": "DAI"}))
    l4 = evaluate_layer4_token_check(crisis_scenario_svb_usdc().layer4.model_copy(update={"symbol": "DAI"}))

    l5_no_contagion = evaluate_layer5_hedge_and_sizing(
        l1, l4, Layer5Input(symbol="DAI", base_size_usd=1000.0, peer_distress_probs={})
    )
    l5_with_contagion = evaluate_layer5_hedge_and_sizing(
        l1, l4, Layer5Input(symbol="DAI", base_size_usd=1000.0, peer_distress_probs={"USDC": 0.90, "FRAX": 0.80})
    )
    assert l5_with_contagion.contagion_brake_factor < l5_no_contagion.contagion_brake_factor
    assert l5_with_contagion.raw_order_size_usd < l5_no_contagion.raw_order_size_usd


# =============================================================================
# Empirical Stress-Testing Plan: The 4 Historical Crisis Scenarios (Page 9)
# =============================================================================


def test_crisis_1_svb_usdc_march_2023_authorized_with_fisco_par_repo():
    """Crisis 1 (March 2023): SVB Collapse & Multi-Coin Contagion (USDC / USDT).
    PegGuard classifies Regime 2 (Temporary Liquidity Distress), authorizes Class B two-leg arbitrage
    via FISCO BCOS Par-Capped USDT Repo, and prevents $1.04 USDT short-squeeze liquidation.
    """
    engine = PegGuardEngine()
    decision = engine.evaluate(crisis_scenario_svb_usdc(order_size_usd=500.0))
    assert decision.authorized is True
    assert decision.layer2.regime == PegRegime.TEMPORARY_LIQUIDITY_DISTRESS
    assert decision.layer4.i_safe_veto == 1
    assert decision.layer5.hedge_class == "CLASS_B_FISCO_PAR_REPO"
    assert decision.layer5.fisco_repo_quote is not None
    assert decision.layer5.fisco_repo_quote.effective_unit_liability == 1.000
    assert decision.layer5.fisco_repo_quote.squeeze_protection_saved_usd > 0.0


def test_crisis_2_terra_ust_may_2022_vetoed_preserving_100_percent_capital():
    """Crisis 2 (May 2022): Terra / UST Terminal Collapse.
    PegGuard switches to Regime 3 (Fundamental Peg Collapse) and triggers Layer 4 Hard Veto (I_SafeVeto=0),
    blocking all buying and preserving 100% of capital.
    """
    engine = PegGuardEngine()
    decision = engine.evaluate(crisis_scenario_terra_ust(order_size_usd=500.0))
    assert decision.authorized is False
    assert decision.layer2.regime == PegRegime.FUNDAMENTAL_PEG_COLLAPSE
    assert decision.layer2.death_spiral_veto is True
    assert decision.layer4.i_safe_veto == 0
    assert decision.layer4.token_score_t == 0.0
    assert decision.layer5.final_order_size_usd == 0.0


def test_crisis_3_steth_3ac_june_2022_authorized_with_eth_perp_hedge():
    """Crisis 3 (June 2022): stETH Liquidity Crisis (stETH / ETH).
    FinBERT (50% weight) confirms Beacon ETH solvency, Curve pool tilt reversal signals exhaustion,
    and Class A Long Spot (stETH) + Short ETH-PERP hedge harvests spread + contango funding rebate.
    """
    engine = PegGuardEngine()
    decision = engine.evaluate(crisis_scenario_steth_3ac(order_size_usd=500.0))
    assert decision.authorized is True
    assert decision.layer2.regime == PegRegime.TEMPORARY_LIQUIDITY_DISTRESS
    assert decision.layer3.signed_funding_cf > 0.0
    assert decision.layer5.hedge_class == "CLASS_A_CRYPTO_PERP"
    assert decision.layer5.short_leg_instrument == "SHORT_ETH_PERP"


def test_crisis_4_order_book_depth_and_panic_slippage_stress_test():
    """Crisis 4 (Page 9): Order-Book Depth & Panic Slippage Stress Test ($10k - $10M).
    Simulates 80% order-book liquidity drop and T+3 redemption bottleneck; verifies small orders pass
    while oversized whale orders ($10M into thin depth) are rejected when panic slippage erodes EV < +15 bps.
    """
    engine = PegGuardEngine()
    # 80% depth drop from $2.5M -> $500k, T+3 redemption delay
    base_svb = crisis_scenario_svb_usdc(order_size_usd=10_000.0)
    stressed_small = base_svb.model_copy(
        update={
            "layer3": base_svb.layer3.model_copy(
                update={"order_size_usd": 10_000.0, "l2_depth_usd": 500_000.0, "tau_redeem_days": 3.0}
            )
        }
    )
    stressed_whale = base_svb.model_copy(
        update={
            "layer3": base_svb.layer3.model_copy(
                update={"order_size_usd": 5_000_000.0, "l2_depth_usd": 500_000.0, "tau_redeem_days": 3.0}
            )
        }
    )

    dec_small = engine.evaluate(stressed_small)
    dec_whale = engine.evaluate(stressed_whale)

    assert dec_small.authorized is True
    assert dec_whale.authorized is False
    assert dec_whale.layer3.panic_slippage > dec_small.layer3.panic_slippage
    assert dec_whale.layer3.passes_ev_gate is False


# =============================================================================
# End-to-End PegGuardArbitrageExecutor & MarketRouter Integration
# =============================================================================


def test_pegguard_executor_executes_class_a_class_b_and_blocks_ust_and_respects_cross_chain_tether():
    """Verifies PegGuardArbitrageExecutor & MarketRouter end-to-end:
    1. Class A (stETH) executes Long Spot + Short ETH-PERP (`0xcca1...`).
    2. Class B (USDC) executes Long Spot + FISCO BCOS Par-Capped USDT Repo (`0xccb2...`).
    3. Regime 3 collapse (UST) is vetoed (`status == 'failed'`) and consumes $0 of cross-chain tether radius.
    4. Cross-Chain Tether Radius locks arbitrage once the $500 daily limit is reached.
    """
    arb_exec = PegGuardArbitrageExecutor()
    router = MarketRouter(arbitrage=arb_exec, daily_limit_usd=500.0)
    account = "0xPegGuardTrader"

    # 1. UST collapse -> Vetoed by PegGuard (status='failed', $0 tether spent)
    res_ust = router.submit(_arb_intent("terra_ust_pool", "UST", usd=200.0), account, market="arbitrage")
    assert res_ust.status == "failed"
    assert "PegGuard ABSTAINED/VETOED UST" in res_ust.detail
    assert router.tether_tracker.get_spent(account) == 0.0

    # 2. Class A: stETH 3AC discount ($250) -> Submitted via Long Spot + Short ETH-PERP
    res_steth = router.submit(_arb_intent("curve_steth_eth", "stETH", usd=250.0), account, market="arbitrage")
    assert res_steth.status == "submitted"
    assert res_steth.tx_hash and res_steth.tx_hash.startswith("0xcca1")
    assert "Class A Two-Leg Arbitrage (stETH)" in res_steth.detail
    assert router.tether_tracker.get_spent(account) == 250.0

    # 3. Class B: USDC SVB discount ($250) -> Submitted via FISCO BCOS Par-Capped USDT Repo
    res_usdc = router.submit(_arb_intent("curve_3pool_usdc", "USDC", usd=250.0), account, market="arbitrage")
    assert res_usdc.status == "submitted"
    assert res_usdc.tx_hash and res_usdc.tx_hash.startswith("0xccb2")
    assert "Class B Two-Leg Arbitrage (USDC via FISCO BCOS Par-Capped USDT Repo)" in res_usdc.detail
    assert "Par-Capped Liability=$250.00, Squeeze Saved=$10.00" in res_usdc.detail
    assert router.tether_tracker.get_spent(account) == 500.0
    assert router.tether_tracker.get_remaining(account) == 0.0

    # 4. Further arbitrage is blocked by Cross-Chain Tether Radius ($500 / $500 spent)
    res_locked = router.submit(_arb_intent("curve_3pool_usdc", "USDC", usd=50.0), account, market="arbitrage")
    assert res_locked.status == "failed"
    assert "Cross-chain tether limit exceeded" in res_locked.detail

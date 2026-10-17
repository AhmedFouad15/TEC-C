"""Autonomous PegGuard De-Peg Scanner & Stateful Unprofitable-Price Watermark Engine.

Architecture:
1. User-Toggleable Option (Not a manual user command):
   - The user can enable or disable the PegGuard arbitrage system at any time (`set_enabled(account, True/False)`).
   - When disabled (`enabled=False`), the scanner is completely idle and never places trades.
   - When enabled (`enabled=True`), the scanner continuously monitors the 24-asset 4-category PegGuard universe
     across Ethereum L1, Arbitrum L2, and FISCO BCOS to detect de-pegs.

2. Stateful Unprofitable-Price Watermark ("Low-Watermark Memory"):
   - When the scanner detects that an asset has de-pegged below its Dual-Anchor `Baseline*(t)`:
   - It first checks whether an `UnprofitableWatermark` is recorded for `(account, symbol)`.
   - If the current price `R_cons(t) >= watermark.unprofitable_price`, the scanner **skips** the 5-layer evaluation
     (`status="skipped_watermark"`) so it does not re-check the same unprofitable trade every second.
   - Only when the price drops **strictly lower** than the recorded unprofitable watermark
     (`R_cons(t) < watermark.unprofitable_price`) does the scanner re-evaluate through all 5 PegGuard layers:
       * If still unprofitable/vetoed (`not decision.authorized`), it updates `watermark.unprofitable_price = R_cons(t)`.
       * If profitable (`decision.authorized == True`), it clears the watermark and executes the two-leg arbitrage
         via `PegGuardArbitrageExecutor` / `MarketRouter`.
   - When an asset recovers back to peg, its watermark is automatically cleared.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from tecc_brain.models import ActionType, CardLabel, ExecutionIntent, usd_to_onchain
from tecc_brain.pegguard.engine import (
    PEGGUARD_ASSET_CATALOG,
    PegGuardDecision,
    PegGuardEngine,
    PegGuardMarketInput,
    calibrate_layer1,
    default_pegguard_input_for_symbol,
    resolve_canonical_symbol,
)

if TYPE_CHECKING:
    from tecc_brain.learning.store import ProfileStore
    from tecc_brain.onchain.executor import MarketRouter, PegGuardArbitrageExecutor

DEFAULT_DEPEG_THRESHOLD = 0.0020  # 20 bps below Baseline*(t) triggers de-peg inspection
WATERMARK_EPSILON = 1e-6


class UnprofitableWatermark(BaseModel):
    """Stateful memory of the last de-peg price at which a 5-layer PegGuard check was unprofitable.
    Prevents re-evaluating the same unprofitable trade every second until the price drops strictly lower.
    """

    symbol: str
    unprofitable_price: float = Field(description="Consensus ratio R_cons(t) that was evaluated and found unprofitable")
    baseline_star: float = Field(description="Dual-Anchor Baseline*(t) at time of evaluation")
    abnormal_spread_delta: float = Field(description="Abnormal spread delta(t) = R_cons(t) - Baseline*(t)")
    ev_bps: float = Field(description="Recovery-Adjusted EV in basis points at unprofitable_price")
    reason: str = Field(description="Rejection summary from the 5-layer PegGuard engine")
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


ScanItemStatus = Literal[
    "at_peg",
    "skipped_watermark",
    "noted_unprofitable",
    "executed",
    "execution_failed",
]


class AssetScanOutcome(BaseModel):
    """Result of scanning a single pegged asset during an autonomous PegGuard tick."""

    symbol: str
    category: str
    anchor_asset: str
    hedge_class: str
    current_price: float = Field(description="Current consensus ratio R_cons(t)")
    baseline_star: float = Field(description="Conservative Dual-Anchor Baseline*(t)")
    abnormal_spread_delta: float = Field(description="R_cons(t) - Baseline*(t)")
    depegged: bool
    status: ScanItemStatus
    watermark_price: float | None = Field(
        None, description="Active unprofitable price watermark (re-checks only when current_price < watermark_price)"
    )
    ev_bps: float | None = None
    decision: PegGuardDecision | None = None
    execution_intent: ExecutionIntent | None = None
    detail: str


class ScanTickReport(BaseModel):
    """Summary of one autonomous PegGuard scan pass across the 4-category asset universe."""

    account: str
    enabled: bool
    status: Literal["disabled", "scanned"]
    scanned_count: int = 0
    depegged_count: int = 0
    skipped_by_watermark_count: int = 0
    noted_unprofitable_count: int = 0
    executed_count: int = 0
    outcomes: list[AssetScanOutcome] = Field(default_factory=list)
    active_watermarks: dict[str, UnprofitableWatermark] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PegGuardAutonomousScanner:
    """User-toggleable autonomous de-peg scanner with stateful unprofitable-price watermarks."""

    def __init__(
        self,
        engine: PegGuardEngine | None = None,
        executor: "PegGuardArbitrageExecutor | None" = None,
        router: "MarketRouter | None" = None,
        store: "ProfileStore | None" = None,
        depeg_threshold: float = DEFAULT_DEPEG_THRESHOLD,
    ) -> None:
        self.engine = engine or PegGuardEngine()
        self._executor = executor
        self._router = router
        self.store = store
        self.depeg_threshold = depeg_threshold
        # account -> enabled bool
        self._enabled_by_account: dict[str, bool] = {}
        # account -> symbol -> UnprofitableWatermark
        self._watermarks: dict[str, dict[str, UnprofitableWatermark]] = {}

    @property
    def executor(self) -> "PegGuardArbitrageExecutor":
        if self._executor is None:
            from tecc_brain.onchain.executor import PegGuardArbitrageExecutor

            self._executor = PegGuardArbitrageExecutor()
        return self._executor

    def is_enabled(self, account: str) -> bool:
        """Returns True if the user has enabled autonomous PegGuard arbitrage for `account`."""
        if account in self._enabled_by_account:
            return self._enabled_by_account[account]
        if self.store is not None:
            profile = self.store.load(account)
            if profile is not None:
                enabled = bool(getattr(profile, "arbitrage_enabled", False))
                self._enabled_by_account[account] = enabled
                return enabled
        return False

    def set_enabled(self, account: str, enabled: bool) -> bool:
        """Toggles autonomous PegGuard arbitrage on or off for `account` at any time."""
        flag = bool(enabled)
        self._enabled_by_account[account] = flag
        if self.store is not None:
            from tecc_brain.graph.pipeline import load_or_create_profile

            profile = load_or_create_profile(self.store, account)
            updated = profile.model_copy(update={"arbitrage_enabled": flag})
            self.store.save(updated)
        return flag

    def enable(self, account: str) -> bool:
        return self.set_enabled(account, True)

    def disable(self, account: str) -> bool:
        return self.set_enabled(account, False)

    def get_watermarks(self, account: str) -> dict[str, UnprofitableWatermark]:
        return dict(self._watermarks.get(account, {}))

    def clear_watermark(self, account: str, symbol: str | None = None) -> None:
        if account not in self._watermarks:
            return
        if symbol is None:
            self._watermarks[account].clear()
        else:
            canonical = resolve_canonical_symbol(symbol)
            self._watermarks[account].pop(canonical, None)

    def _build_calm_or_overridden_input(
        self,
        symbol: str,
        order_size_usd: float,
        price_overrides: dict[str, float] | None,
        market_inputs: dict[str, PegGuardMarketInput] | None,
    ) -> PegGuardMarketInput:
        canonical = resolve_canonical_symbol(symbol)
        if market_inputs and (canonical in market_inputs or symbol in market_inputs):
            inp = market_inputs.get(canonical) or market_inputs[symbol]
            if price_overrides and (canonical in price_overrides or symbol in price_overrides):
                override_r = price_overrides.get(canonical, price_overrides.get(symbol))
                if override_r is not None:
                    p_anchor = inp.layer1.p_anchor_usdt
                    inp = inp.model_copy(
                        update={
                            "layer1": inp.layer1.model_copy(
                                update={"r_direct": override_r, "p_pegged_usdt": round(override_r * p_anchor, 6)}
                            )
                        }
                    )
            return inp

        if price_overrides and (canonical in price_overrides or symbol in price_overrides):
            override_r = price_overrides.get(canonical, price_overrides.get(symbol))
            return default_pegguard_input_for_symbol(canonical, order_size_usd=order_size_usd, current_ratio=override_r)

        # Default calm state when no override is supplied: asset trades at its par/equilibrium ratio
        spec = PEGGUARD_ASSET_CATALOG.get(canonical)
        calm_ratio = spec.p_par if spec is not None else 1.000
        return default_pegguard_input_for_symbol(canonical, order_size_usd=order_size_usd, current_ratio=calm_ratio)

    def scan_tick(
        self,
        account: str,
        *,
        price_overrides: dict[str, float] | None = None,
        market_inputs: dict[str, PegGuardMarketInput] | None = None,
        symbols: list[str] | None = None,
        order_size_usd: float = 250.0,
    ) -> ScanTickReport:
        """Runs one continuous monitoring pass across the PegGuard asset universe for `account`.

        - If `is_enabled(account)` is False, returns immediately with `status='disabled'`.
        - For each asset that has de-pegged (`R_cons(t) < Baseline*(t) - depeg_threshold`):
          * If an `UnprofitableWatermark` exists and `R_cons(t) >= watermark.unprofitable_price`,
            skips the 5-layer evaluation (`status='skipped_watermark'`).
          * If no watermark exists OR `R_cons(t) < watermark.unprofitable_price`, runs all 5 PegGuard layers:
            - If unprofitable/vetoed: updates `watermark.unprofitable_price = R_cons(t)` (`status='noted_unprofitable'`).
            - If profitable/authorized: clears the watermark and submits the trade (`status='executed'`).
        """
        if not self.is_enabled(account):
            return ScanTickReport(
                account=account,
                enabled=False,
                status="disabled",
                active_watermarks=self.get_watermarks(account),
            )

        if symbols is not None:
            scan_symbols = [resolve_canonical_symbol(s) for s in symbols]
        else:
            scan_symbols = list(PEGGUARD_ASSET_CATALOG.keys())
            if price_overrides:
                for k in price_overrides:
                    ck = resolve_canonical_symbol(k)
                    if ck not in scan_symbols:
                        scan_symbols.append(ck)
            if market_inputs:
                for k in market_inputs:
                    ck = resolve_canonical_symbol(k)
                    if ck not in scan_symbols:
                        scan_symbols.append(ck)

        acct_watermarks = self._watermarks.setdefault(account, {})
        outcomes: list[AssetScanOutcome] = []
        depegged_count = 0
        skipped_count = 0
        noted_unprofitable_count = 0
        executed_count = 0

        for sym in scan_symbols:
            spec = PEGGUARD_ASSET_CATALOG.get(sym)
            category = spec.category if spec else "1_FIAT_AND_DECENTRALIZED_STABLECOINS"
            anchor_asset = spec.anchor_asset if spec else "USD"
            hedge_class = spec.hedge_class if spec else "CLASS_B_FISCO_PAR_REPO"
            venue_id = spec.primary_long_venue if spec else f"pegguard_{sym.lower()}_pool"

            pg_input = self._build_calm_or_overridden_input(
                sym, order_size_usd=order_size_usd, price_overrides=price_overrides, market_inputs=market_inputs
            )
            l1 = calibrate_layer1(pg_input.layer1.model_copy(update={"symbol": sym}))
            r_cons = l1.r_cons
            baseline_star = l1.baseline_star
            delta = l1.abnormal_spread_delta

            is_depegged = delta < -self.depeg_threshold

            if not is_depegged:
                # Recovered to peg -> clear any prior unprofitable watermark for this symbol
                acct_watermarks.pop(sym, None)
                outcomes.append(
                    AssetScanOutcome(
                        symbol=sym,
                        category=category,
                        anchor_asset=anchor_asset,
                        hedge_class=hedge_class,
                        current_price=r_cons,
                        baseline_star=baseline_star,
                        abnormal_spread_delta=delta,
                        depegged=False,
                        status="at_peg",
                        detail=f"{sym} is at peg (R_cons={r_cons:.4f}, Baseline*={baseline_star:.4f}, delta={delta:+.4f})",
                    )
                )
                continue

            depegged_count += 1
            existing_wm = acct_watermarks.get(sym)

            # Check Stateful Unprofitable-Price Watermark:
            # Only re-evaluate if current price went strictly LOWER than the noted unprofitable price!
            if existing_wm is not None and r_cons >= existing_wm.unprofitable_price - WATERMARK_EPSILON:
                skipped_count += 1
                outcomes.append(
                    AssetScanOutcome(
                        symbol=sym,
                        category=category,
                        anchor_asset=anchor_asset,
                        hedge_class=hedge_class,
                        current_price=r_cons,
                        baseline_star=baseline_star,
                        abnormal_spread_delta=delta,
                        depegged=True,
                        status="skipped_watermark",
                        watermark_price=existing_wm.unprofitable_price,
                        ev_bps=existing_wm.ev_bps,
                        detail=(
                            f"Skipped 5-layer re-check for {sym}: current price {r_cons:.4f} >= noted unprofitable "
                            f"watermark {existing_wm.unprofitable_price:.4f} (will only re-check when price drops < "
                            f"{existing_wm.unprofitable_price:.4f})"
                        ),
                    )
                )
                continue

            # Price is a fresh de-peg OR dropped strictly lower than the previous unprofitable price -> Run all 5 Layers!
            decision = self.engine.evaluate(pg_input)

            if not decision.authorized:
                noted_unprofitable_count += 1
                wm = UnprofitableWatermark(
                    symbol=sym,
                    unprofitable_price=r_cons,
                    baseline_star=decision.layer1.baseline_star,
                    abnormal_spread_delta=decision.layer1.abnormal_spread_delta,
                    ev_bps=decision.layer3.recovery_adjusted_ev_bps,
                    reason=decision.summary,
                )
                acct_watermarks[sym] = wm
                outcomes.append(
                    AssetScanOutcome(
                        symbol=sym,
                        category=category,
                        anchor_asset=anchor_asset,
                        hedge_class=hedge_class,
                        current_price=r_cons,
                        baseline_star=decision.layer1.baseline_star,
                        abnormal_spread_delta=decision.layer1.abnormal_spread_delta,
                        depegged=True,
                        status="noted_unprofitable",
                        watermark_price=r_cons,
                        ev_bps=decision.layer3.recovery_adjusted_ev_bps,
                        decision=decision,
                        detail=(
                            f"Noted unprofitable watermark for {sym} at {r_cons:.4f} "
                            f"(EV={decision.layer3.recovery_adjusted_ev_bps:+.1f} bps): {decision.summary}. "
                            f"Will skip until price drops below {r_cons:.4f}."
                        ),
                    )
                )
                continue

            # Profitable & authorized by all 5 layers -> Clear watermark and execute via PegGuardArbitrageExecutor!
            acct_watermarks.pop(sym, None)
            exec_size_usd = decision.layer5.final_order_size_usd
            intent = ExecutionIntent(
                card_label=CardLabel.OPPORTUNITY,
                venue_id=venue_id,
                action=ActionType.BUY_DISCOUNT,
                asset_in=sym,
                amount_usd=exec_size_usd,
                amount_onchain=usd_to_onchain(exec_size_usd),
                market="arbitrage",
            )
            if self._router is not None:
                self.executor.market_inputs[sym] = pg_input
                exec_res = self._router.submit(intent, account, market="arbitrage")
            else:
                exec_res = self.executor.submit(intent, account, market_input=pg_input)

            if exec_res.status in ("submitted", "simulated"):
                executed_count += 1
                item_status: ScanItemStatus = "executed"
            else:
                item_status = "execution_failed"

            outcomes.append(
                AssetScanOutcome(
                    symbol=sym,
                    category=category,
                    anchor_asset=anchor_asset,
                    hedge_class=hedge_class,
                    current_price=r_cons,
                    baseline_star=decision.layer1.baseline_star,
                    abnormal_spread_delta=decision.layer1.abnormal_spread_delta,
                    depegged=True,
                    status=item_status,
                    watermark_price=None,
                    ev_bps=decision.layer3.recovery_adjusted_ev_bps,
                    decision=decision,
                    execution_intent=exec_res,
                    detail=exec_res.detail,
                )
            )

        return ScanTickReport(
            account=account,
            enabled=True,
            status="scanned",
            scanned_count=len(scan_symbols),
            depegged_count=depegged_count,
            skipped_by_watermark_count=skipped_count,
            noted_unprofitable_count=noted_unprofitable_count,
            executed_count=executed_count,
            outcomes=outcomes,
            active_watermarks=dict(acct_watermarks),
        )

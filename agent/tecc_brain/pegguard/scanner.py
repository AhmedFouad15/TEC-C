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
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

from tecc_brain.models import ActionType, CardLabel, ExecutionIntent, usd_to_onchain
from tecc_brain.onchain.audit_anchor import compute_audit_record_hash
from tecc_brain.pegguard.engine import (
    PEGGUARD_ASSET_CATALOG,
    PegGuardDecision,
    PegGuardEngine,
    PegGuardMarketInput,
    calibrate_layer1,
    default_pegguard_input_for_symbol,
    resolve_canonical_symbol,
)

from tecc_brain.graph.brain import BrainReport

if TYPE_CHECKING:
    from tecc_brain.learning.store import ProfileStore
    from tecc_brain.models import VaultState
    from tecc_brain.onchain.anchoring import AuditAnchorService
    from tecc_brain.reference import Reference
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
    audit_record_hash: str | None = Field(
        None,
        description="Privacy-Preserving SHA-256 audit anchor committed to FISCO BCOS: SHA256(account || symbol || action || P_cons || timestamp || salt)",
    )


ScanItemStatus = Literal[
    "at_peg",
    "skipped_watermark",
    "noted_unprofitable",
    "executed",
    "execution_failed",
    "held_for_approval",  # authorized by PegGuard, but the soft tether or the AI Brain left it for the user
    "vetoed_by_brain",  # authorized by PegGuard, vetoed by the AI Brain (tighten-only)
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
    audit_record_hash: str | None = Field(
        None,
        description="Privacy-Preserving SHA-256 audit anchor committed to FISCO BCOS: SHA256(account || symbol || action || P_cons || timestamp || salt)",
    )
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
    held_count: int = 0
    outcomes: list[AssetScanOutcome] = Field(default_factory=list)
    brain_report: BrainReport | None = Field(
        None, description="The AI Brain's decision over every PegGuard-authorized trade in this tick (same contract as /propose)"
    )
    proposal_id: str | None = Field(None, description="Approve a held trade with POST /api/mandate/execute (label OPPORTUNITY)")
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
        anchors: "AuditAnchorService | None" = None,
    ) -> None:
        self.anchors = anchors
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

    def _brain_gate(
        self, account: str, items: list[dict[str, Any]], *, vault: "VaultState | None", brain_llm: Any,
        ref: "Reference | None", proposals: Any,
    ) -> tuple[list[AssetScanOutcome], "BrainReport", str | None]:
        """PegGuard-authorized trades → soft tether → AI Brain (tighten-only) → MarketRouter. Never more than the
        user's soft tether runs automatically; anything else is held for approval or vetoed."""
        from tecc_brain.graph.brain import build_brain_input, synthesize
        from tecc_brain.graph.pipeline import PipelineResult, load_or_create_profile
        from tecc_brain.intent.firewall import scan
        from tecc_brain.intent.rules import ParseOutcome
        from tecc_brain.learning.update import new_profile
        from tecc_brain.market import SnapshotSource
        from tecc_brain.models import AutonomyMode, Candidate, Card, Decision, Mandate, RiskTier, VaultState
        from tecc_brain.reference import load_reference
        from tecc_brain.strategy.market_view import assess_market
        from tecc_brain.strategy.planner import soft_limit

        ref = ref or load_reference()
        vault = vault or VaultState(tether_radius_usd=self._router.daily_limit_usd if self._router else 500.0)
        profile = load_or_create_profile(self.store, account) if self.store is not None else new_profile(account, RiskTier.BALANCED)
        items = sorted(items, key=lambda it: it["decision"].layer3.recovery_adjusted_ev_bps, reverse=True)

        limit = soft_limit(profile, vault)
        remaining = limit
        cards: list[Card] = []
        caps: list[float] = []
        for it in items:
            d, sym = it["decision"], it["symbol"]
            size = d.layer5.final_order_size_usd
            ev = d.layer3.recovery_adjusted_ev_bps
            cand = Candidate(venue_id=it["venue_id"], action=ActionType.BUY_DISCOUNT, asset_in=sym, amount_usd=size,
                             apy=max(ev, 0.0) / 1e4)
            lines = [f"PegGuard: all 5 layers authorized ({d.summary}).", f"Recovery-adjusted EV {ev:+.1f} bps."]
            if remaining > 0:
                alloc = min(size, remaining)
                remaining -= alloc
                mode = AutonomyMode.AUTO
                if alloc < size:
                    lines.append(f"Soft tether: ${alloc:,.0f} of ${size:,.0f} runs now; the rest needs your approval.")
            else:
                alloc = 0.0
                mode = AutonomyMode.BREAKOUT if size > vault.remaining_usd else AutonomyMode.PROPOSE
                lines.append("Today's soft tether is already used: needs your approval"
                             + (" with FaceID (above the vault radius)." if mode == AutonomyMode.BREAKOUT else "."))
            caps.append(alloc if mode == AutonomyMode.AUTO else size)
            cards.append(Card(label=CardLabel.OPPORTUNITY, candidate=cand, mode=mode, market="arbitrage",
                              headline=f"PegGuard: buy {sym} at {it['r_cons']:.4f}", explanation=lines))

        total = sum(c.candidate.amount_usd for c in cards)
        auto = sum(cap for cap, c in zip(caps, cards) if c.mode == AutonomyMode.AUTO)
        baseline = Decision(
            mandate=Mandate(raw_text="pegguard:scan", action=ActionType.BUY_DISCOUNT, asset=items[0]["symbol"],
                            amount=total, amount_usd=total),
            mode=AutonomyMode.AUTO if auto > 0 else AutonomyMode.PROPOSE, auto_amount_usd=auto,
            proposed_amount_usd=max(0.0, total - auto), cards=cards,
            trace=[f"PegGuard authorized {len(cards)} trade(s); soft tether ${limit:,.0f}."],
        )
        snapshot = SnapshotSource("demo").snapshot()
        payload = build_brain_input(baseline, total, profile, vault, snapshot, assess_market(snapshot, ref), ref)
        for i, cand in enumerate(payload["candidates"]):
            cand["max_amount_usd"] = round(caps[i], 2)
            cand["exposed_to"] = [items[i]["symbol"]]
        payload["mandate"] = {
            "kind": "pegguard_arbitrage", "amount_usd": round(total, 2),
            "opportunities": [{"symbol": it["symbol"], "hedge_class": it["hedge_class"],
                               "ev_bps": round(it["decision"].layer3.recovery_adjusted_ev_bps, 2),
                               "current_ratio": round(it["r_cons"], 6)} for it in items],
        }
        final, report = synthesize(baseline, payload, brain_llm)
        auto_by = {a.candidate_id: a.amount_usd for a in report.allocations if a.mode == AutonomyMode.AUTO}

        arbitrage_exec = self._router.arbitrage if self._router is not None else self.executor
        outcomes: list[AssetScanOutcome] = []
        auto_executed: dict[str, float] = {}
        for i, (card, it) in enumerate(zip(final.cards, items)):
            sym, d = it["symbol"], it["decision"]
            arbitrage_exec.market_inputs[sym] = it["pg_input"]  # /execute re-checks a held trade with this input
            exec_res = None
            if card.mode == AutonomyMode.AUTO:
                amount = min(auto_by.get(f"c{i}", 0.0), caps[i])
                intent = ExecutionIntent(card_label=CardLabel.OPPORTUNITY, venue_id=it["venue_id"],
                                         action=ActionType.BUY_DISCOUNT, asset_in=sym, amount_usd=amount,
                                         amount_onchain=usd_to_onchain(amount), market="arbitrage")
                if self._router is not None:
                    exec_res = self._router.submit(intent, account, market="arbitrage", limit_usd=vault.tether_radius_usd)
                else:
                    exec_res = self.executor.submit(intent, account, market_input=it["pg_input"])
                status: ScanItemStatus = "executed" if exec_res.status in ("submitted", "simulated") else "execution_failed"
                if status == "executed":
                    auto_executed[card.candidate.venue_id] = exec_res.amount_usd
                detail = exec_res.detail
            elif card.mode == AutonomyMode.BLOCKED:
                status, detail = "vetoed_by_brain", f"AI Brain vetoed this trade: {report.user_explanation}"
            else:
                status = "held_for_approval"
                detail = (f"Held for your approval ({card.mode.value}): " + " ".join(card.explanation[2:])).strip()
            outcomes.append(AssetScanOutcome(
                symbol=sym, category=it["category"], anchor_asset=it["anchor_asset"], hedge_class=it["hedge_class"],
                current_price=it["r_cons"], baseline_star=d.layer1.baseline_star,
                abnormal_spread_delta=d.layer1.abnormal_spread_delta, depegged=True, status=status,
                ev_bps=d.layer3.recovery_adjusted_ev_bps, decision=d, execution_intent=exec_res,
                audit_record_hash=exec_res.audit_record_hash if exec_res else None, detail=detail,
            ))

        proposal_id = None
        open_cards = [c for c in final.cards if c.mode != AutonomyMode.BLOCKED
                      and auto_executed.get(c.candidate.venue_id, 0.0) < c.candidate.amount_usd - 0.01]
        if proposals is not None and open_cards:
            record = PipelineResult(status="decided", decision=final, brain_report=report,
                                    parse=ParseOutcome(mandate=final.mandate, verdict=scan(final.mandate.raw_text)))
            proposal_id = proposals.add(account, record, vault, auto_executed_usd=auto_executed)
        return outcomes, report, proposal_id

    def scan_tick(
        self,
        account: str,
        *,
        price_overrides: dict[str, float] | None = None,
        market_inputs: dict[str, PegGuardMarketInput] | None = None,
        symbols: list[str] | None = None,
        order_size_usd: float = 250.0,
        vault: "VaultState | None" = None,
        brain_llm: Any = None,
        ref: "Reference | None" = None,
        proposals: Any = None,
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
        held_count = 0
        authorized: list[dict[str, Any]] = []

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
                depeg_hash = compute_audit_record_hash(
                    account=account,
                    symbol=sym,
                    action="DEPEG_DETECTED",
                    p_cons=r_cons,
                    salt=f"L1_{decision.layer1.baseline_star:.4f}",
                )
                wm = UnprofitableWatermark(
                    symbol=sym,
                    unprofitable_price=r_cons,
                    baseline_star=decision.layer1.baseline_star,
                    abnormal_spread_delta=decision.layer1.abnormal_spread_delta,
                    ev_bps=decision.layer3.recovery_adjusted_ev_bps,
                    reason=decision.summary,
                    audit_record_hash=depeg_hash,
                )
                acct_watermarks[sym] = wm
                overridden = bool(price_overrides) and any(resolve_canonical_symbol(k) == sym for k in price_overrides)
                if self.anchors is not None and not overridden:  # a caller-supplied price is not a market fact
                    from tecc_brain.onchain.audit_anchor import AuditRecordType

                    self.anchors.anchor(depeg_hash, AuditRecordType.DEPEG_DETECTED)
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
                        audit_record_hash=depeg_hash,
                        detail=(
                            f"Noted unprofitable watermark for {sym} at {r_cons:.4f} "
                            f"(EV={decision.layer3.recovery_adjusted_ev_bps:+.1f} bps): {decision.summary}. "
                            f"Will skip until price drops below {r_cons:.4f}."
                        ),
                    )
                )
                continue

            # Authorized by all 5 layers. B3: PegGuard is the deterministic Level 2 — it never executes on its own.
            # Every authorized trade goes to the AI Brain with the soft tether and the vault radius, then through the
            # MarketRouter's cross-chain tether tracker, exactly like /propose and /evaluate_options.
            acct_watermarks.pop(sym, None)
            authorized.append({
                "symbol": sym, "category": category, "anchor_asset": anchor_asset, "hedge_class": hedge_class,
                "venue_id": venue_id, "r_cons": r_cons, "decision": decision, "pg_input": pg_input,
            })

        report = None
        proposal_id = None
        if authorized:
            gated, report, proposal_id = self._brain_gate(account, authorized, vault=vault, brain_llm=brain_llm,
                                                          ref=ref, proposals=proposals)
            for outcome in gated:
                executed_count += outcome.status == "executed"
                held_count += outcome.status == "held_for_approval"
            outcomes.extend(gated)

        return ScanTickReport(
            account=account,
            enabled=True,
            status="scanned",
            scanned_count=len(scan_symbols),
            depegged_count=depegged_count,
            skipped_by_watermark_count=skipped_count,
            noted_unprofitable_count=noted_unprofitable_count,
            executed_count=executed_count,
            held_count=held_count,
            outcomes=outcomes,
            brain_report=report,
            proposal_id=proposal_id,
            active_watermarks=dict(acct_watermarks),
        )

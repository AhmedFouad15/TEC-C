"""The planner: one mandate in, one explainable Decision out (BRAIN_DESIGN §2.2–2.3, §2.5–2.6).

Steps: market view → candidates → hard filters → loss-averse scores → Good/Better/Best → autonomy gate
(soft tether, split sizing) → portfolio cards (reduce exposure, opportunities).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tecc_brain.models import (
    APPROVAL_THRESHOLDS,
    ActionType,
    AutonomyMode,
    BrainProfile,
    Candidate,
    Card,
    CardLabel,
    Decision,
    MarketSnapshot,
    Mandate,
    NotePreference,
    Portfolio,
    ScoreBreakdown,
    VaultState,
    Venue,
)
from tecc_brain.reference import Reference, read_data_json
from tecc_brain.risk.filters import REASON_TEXT, FilterContext, hard_filter_reasons
from tecc_brain.risk.score import score_venue
from tecc_brain.strategy.market_view import MarketView, assess_market
from tecc_brain.strategy.playbook import opportunity_cards, reduce_exposure_cards
from tecc_brain.strategy.portfolio import portfolio_risk

AUTO_MIN_P_NORMAL = 0.80
NEWS_AUTONOMY_THRESHOLD = 0.60  # bad news removes autonomy (PROPOSE only); it never vetoes on its own
SAFE_HARBOUR_TOLERANCE = -0.001  # the hurdle rail scores ≈ 0 by construction; still a valid "Good" choice


def load_demo_profile() -> BrainProfile:
    return BrainProfile.model_validate(read_data_json("profile_demo.json"))


def soft_limit(profile: BrainProfile, vault: VaultState) -> float:
    """The Brain's own tether, below the vault's: (0.5 + 0.5·τ) × remaining radius."""
    return (0.5 + 0.5 * profile.tau) * vault.remaining_usd


def mandate_amount_usd(mandate: Mandate, snapshot: MarketSnapshot) -> tuple[float | None, bool]:
    """(USD value, verified). Fails closed: never guesses a price, and never trusts a caller-supplied
    amount_usd that is smaller than units × market price (an understated value could slip under the tether)."""
    price = snapshot.prices_usd.get(mandate.asset)
    computed = mandate.amount * price if price is not None else None
    if computed is None:
        return mandate.amount_usd, False
    if mandate.amount_usd is None:
        return computed, True
    return max(computed, mandate.amount_usd), True


def protocol_stance(profile: BrainProfile, protocol: str) -> NotePreference | None:
    """The user's latest note about this protocol, if any (later notes override earlier ones)."""
    return next((p for p in reversed(profile.preferences) if p.protocol == protocol), None)


def _auto_blockers(venue: Venue, profile: BrainProfile, view: MarketView, snapshot: MarketSnapshot, ref: Reference) -> list[str]:
    blockers = []
    stance = protocol_stance(profile, venue.protocol)
    if stance is not None and stance.polarity < 0:
        blockers.append(f"you asked to avoid {venue.protocol}" + (f" (“{stance.quote}”)" if stance.quote else ""))
    threshold = APPROVAL_THRESHOLDS[profile.tier]
    if not profile.has_history(venue.id):
        blockers.append("first use of this protocol — needs your approval")
    elif profile.approval_mean(venue.id) < threshold:
        blockers.append(f"your approval rate here ({profile.approval_mean(venue.id):.0%}) is below {threshold:.0%}")
    for symbol in venue.exposures:
        a = view.assessments.get(symbol)
        if a is None:
            blockers.append(f"no live peg data for {symbol}")
            continue
        if a.probs.p_normal < AUTO_MIN_P_NORMAL:
            blockers.append(f"{symbol} is not trading normally (P normal {a.probs.p_normal:.0%})")
        cluster = view.cluster_of(symbol, ref)
        if cluster and cluster.stressed:
            blockers.append(f"the {cluster.cluster} cluster is under stress")
    keys = {venue.protocol.lower(), venue.name.lower()}
    for news in snapshot.news:
        if news.p_negative >= NEWS_AUTONOMY_THRESHOLD and any(news.entity.lower() in k for k in keys):
            blockers.append(f"negative news on {news.entity} ({news.p_negative:.0%})")
    return list(dict.fromkeys(blockers))


def _personal_lines(profile: BrainProfile, venue: Venue) -> list[str]:
    lines = []
    stance = protocol_stance(profile, venue.protocol)
    if stance is not None and stance.polarity > 0 and stance.quote:
        lines.append(f"You said: “{stance.quote}”.")
    for factor, label in (("c_in", "Entry cost"), ("c_out_stress", "Panic-exit cost")):
        weight = profile.cost_factors.get(factor, 1.0)
        if weight != 1.0:
            lines.append(f"{label} weighted ×{weight:.2f} because of your review notes.")
    return lines


def _metric_lines(s: ScoreBreakdown) -> list[str]:
    if s.cvar_95 is None:
        return []
    sharpe = f"Sharpe {s.sharpe:.2f} vs Shibor" if s.sharpe is not None else "Sharpe n/a (riskless)"
    tail = (
        f"average loss in the worst 5% of years (CVaR 95%) {s.cvar_95 * 100:.1f}%"
        if s.cvar_95 > 0
        else f"even the worst 5% of years average {-s.cvar_95 * 100:+.1f}% (CVaR 95%)"
    )
    return [f"{sharpe} · {tail}."]


def _card(label: CardLabel, candidate: Candidate, venue: Venue, mode: AutonomyMode, extra: list[str]) -> Card:
    s = candidate.score
    assert s is not None
    return Card(
        label=label,
        candidate=candidate,
        mode=mode,
        headline=f"{venue.name}: {s.total * 100:+.2f}%/yr after expected losses and panic-exit cost",
        explanation=[
            f"Yield {candidate.apy * 100:.2f}% vs 1Y Shibor hurdle → excess {s.excess_yield * 100:+.2f}%.",
            f"Permanent-loss risk {s.pd * 100:.2f}% × loss {s.lgd:.0%}, weighted by your loss aversion → −{s.loss_weighted * 100:.2f}%.",
            f"Entry {s.c_in * 100:.2f}% and panic-exit cost {s.c_out_stress * 100:.2f}% included.",
            *(
                [f"You have approved this protocol before: {s.affinity_term * 100:+.2f}% personal preference."]
                if s.affinity_term > 0
                else [f"You have pushed back on this protocol before: {s.affinity_term * 100:+.2f}%."]
                if s.affinity_term < 0
                else []
            ),
            f"Risk-adjusted: {s.total * 100:+.2f}%/yr.",
            *_metric_lines(s),
            *extra,
        ],
    )


@dataclass
class OptionsAssessment:
    """What the Econometric & Liquidity agent hands to the Gatekeeper: every option sized, filtered and scored."""

    mandate: Mandate
    amount_usd: float | None
    verified: bool
    view: MarketView
    passing: list[tuple[Venue, Candidate]] = field(default_factory=list)
    rejected: list[Candidate] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)


def assess_options(
    mandate: Mandate,
    snapshot: MarketSnapshot,
    profile: BrainProfile,
    vault: VaultState,
    ref: Reference,
    view: MarketView | None = None,
) -> OptionsAssessment:
    """Size the request, apply the hard filters and score every venue that accepts the asset."""
    view = view if view is not None else assess_market(snapshot, ref)
    amount, verified = mandate_amount_usd(mandate, snapshot)
    out = OptionsAssessment(mandate=mandate, amount_usd=amount, verified=verified, view=view)
    if amount is None:
        out.trace.append(f"Blocked: no market price for {mandate.asset}, so the request cannot be sized safely.")
        return out
    stressed = [c.cluster for c in view.clusters.values() if c.stressed]
    out.trace.append(f"Request: {mandate.action.value} ${amount:,.0f} of {mandate.asset}.")
    out.trace.append(f"Market: hurdle {snapshot.hurdle_rate * 100:.2f}% (1Y Shibor); stressed clusters: {', '.join(stressed) or 'none'}.")

    ctx = FilterContext(tier=profile.tier, whitelist=vault.whitelist, heartbeat_alive=vault.heartbeat_alive)
    avoid = {c.split(":", 1)[1] for c in mandate.constraints if c.startswith("avoid:")}
    only = {c.split(":", 1)[1] for c in mandate.constraints if c.startswith("venue:")}
    for venue in ref.venues.values():
        if mandate.asset not in venue.accepts or venue.id not in snapshot.venues:
            continue
        quote = snapshot.venues[venue.id]
        candidate = Candidate(venue_id=venue.id, action=venue.action, asset_in=mandate.asset, amount_usd=amount, apy=quote.apy)
        if venue.protocol in avoid or (only and venue.protocol not in only):
            # The user's own words (or a standing preference they approved at /draft) — never overridden by score.
            candidate.rejected_reasons = ["user_constraint"]
            out.rejected.append(candidate)
            why = f"you asked to avoid {venue.protocol}" if venue.protocol in avoid else f"you asked for {', '.join(sorted(only))} only"
            out.trace.append(f"Rejected {venue.id}: user_constraint — {why}.")
            continue
        reasons = hard_filter_reasons(venue, quote, amount, view.assessments, ctx)
        if reasons:
            candidate.rejected_reasons = [r.value for r in reasons]
            out.rejected.append(candidate)
            out.trace.append(f"Rejected {venue.id}: {', '.join(r.value for r in reasons)} — {REASON_TEXT[reasons[0]]}")
            continue
        candidate.score = score_venue(
            venue, quote, snapshot, view.assessments,
            lam=profile.lam, affinity=profile.affinity(venue.id), horizon_days=mandate.horizon_days,
            cost_factors=profile.cost_factors,
        )
        out.passing.append((venue, candidate))
        out.trace.append(f"Scored {venue.id}: {candidate.score.total * 100:+.2f}%/yr.")
    return out


def decide(
    assessment: OptionsAssessment,
    snapshot: MarketSnapshot,
    portfolio: Portfolio,
    profile: BrainProfile,
    vault: VaultState,
    ref: Reference,
) -> Decision:
    """Good/Better/Best, the autonomy gate (soft tether, split sizing) and the portfolio cards."""
    mandate, amount, verified, view = assessment.mandate, assessment.amount_usd, assessment.verified, assessment.view
    passing, rejected = assessment.passing, assessment.rejected
    trace = list(assessment.trace)
    if amount is None:
        return Decision(mandate=mandate, mode=AutonomyMode.BLOCKED, trace=trace)

    limit = soft_limit(profile, vault)
    if not verified:
        trace.append(f"No market price for {mandate.asset}: the stated value cannot be verified, so nothing runs automatically.")
    trace.append(f"Soft tether: (0.5 + 0.5·τ={profile.tau:.2f}) × ${vault.remaining_usd:,.0f} remaining = ${limit:,.0f}.")

    def total(vc: tuple[Venue, Candidate]) -> float:
        return vc[1].score.total  # type: ignore[union-attr]

    positive = [vc for vc in passing if total(vc) > 0]
    blockers = {v.id: _auto_blockers(v, profile, view, snapshot, ref) for v, _ in passing}
    if not verified:
        for venue_id in blockers:
            blockers[venue_id].append(f"value of {mandate.asset} not verifiable from market prices")
    eligible = [vc for vc in positive if not blockers[vc[0].id]]

    if mandate.action == ActionType.OPTIMIZE_YIELD:
        harbour = [vc for vc in passing if total(vc) >= SAFE_HARBOUR_TOLERANCE]
        good = min(harbour, key=lambda vc: vc[1].score.expected_loss) if harbour else None  # type: ignore[union-attr]
    else:
        literal = [vc for vc in passing if vc[0].action == mandate.action]
        good = max(literal, key=total) if literal else None
    best = max(positive, key=total) if positive else None
    better = max(eligible, key=total) if eligible else None

    picks: list[tuple[CardLabel, tuple[Venue, Candidate]]] = []
    for label, pick in ((CardLabel.BEST, best), (CardLabel.BETTER, better), (CardLabel.GOOD, good)):
        if pick and all(pick[0].id != p[1][0].id for p in picks):
            picks.append((label, pick))

    auto_amount = 0.0
    cards: list[Card] = []
    for label, (venue, candidate) in picks:
        extra: list[str] = []
        if better is not None and venue.id == better[0].id and limit > 0:
            mode = AutonomyMode.AUTO
            auto_amount = min(amount, limit)
            extra.append(f"Runs ${auto_amount:,.0f} now inside your soft tether.")
            if amount > auto_amount:
                extra.append(f"The remaining ${amount - auto_amount:,.0f} is proposed for your approval.")
        elif amount > vault.remaining_usd:
            mode = AutonomyMode.BREAKOUT
            extra.append(f"${amount:,.0f} exceeds today's ${vault.remaining_usd:,.0f} radius → FaceID to break the tether.")
        else:
            mode = AutonomyMode.PROPOSE
        extra += _personal_lines(profile, venue)
        extra += [f"Not automatic: {b}." for b in blockers[venue.id]]
        cards.append(_card(label, candidate, venue, mode, extra))
        trace.append(f"{label.value}: {venue.id} ({mode.value}).")

    if vault.heartbeat_alive:
        risk = portfolio_risk(portfolio, view, ref, profile.tier)
        cards += reduce_exposure_cards(portfolio, view, risk, ref)
        cards += opportunity_cards(view, snapshot, ref, budget_usd=limit)

    if auto_amount > 0:
        mode = AutonomyMode.AUTO
    elif cards:
        mode = AutonomyMode.PROPOSE
    else:
        mode = AutonomyMode.BLOCKED
        trace.append("Blocked: no option passes your risk rules.")

    return Decision(
        mandate=mandate,
        mode=mode,
        auto_amount_usd=auto_amount,
        proposed_amount_usd=amount - auto_amount if picks else 0.0,
        cards=cards,
        rejected=rejected,
        trace=trace,
    )


def plan(
    mandate: Mandate,
    snapshot: MarketSnapshot,
    portfolio: Portfolio,
    profile: BrainProfile,
    vault: VaultState,
    ref: Reference,
) -> Decision:
    return decide(assess_options(mandate, snapshot, profile, vault, ref), snapshot, portfolio, profile, vault, ref)

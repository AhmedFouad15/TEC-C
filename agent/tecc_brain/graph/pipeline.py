"""The Brain as a LangGraph multi-agent graph — the team's architecture (BRAIN_DESIGN §1, team notes):

    gatekeeper_intake ─▶ profile ─▶ nlp_sentinel ─▶ econometric_liquidity ─▶ gatekeeper_aggregator ─▶ brain ─▶ web3_executor
    (firewall, parse,             (market + news    (hard filters, score,     (Good/Better/Best,        (one optional  (sign + send;
     privacy sieve)                → 3 regimes,      Sharpe, CVaR)             autonomy gate: the        LLM pass that   Phase 7)
                                     contagion)                                 rule-based baseline)      can only tighten;
                                                                                                          → BrainReport JSON)

Refused or unparseable text stops after intake (no market agent ever sees it); a BLOCKED decision never reaches the
executor. Each agent reports its own lines for the UI. LangSmith tracing is never enabled: nothing leaves the machine.
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from tecc_brain.graph.brain import BRAIN_TIMEOUT_S, BrainLLM, BrainReport, build_brain_input, synthesize
from tecc_brain.intent.firewall import scan
from tecc_brain.intent.parser import IntentParser, default_parser
from tecc_brain.intent.rules import ParseOutcome
from tecc_brain.intent.sieve import mask
from tecc_brain.learning.store import ProfileStore
from tecc_brain.learning.update import new_profile
from tecc_brain.market import SnapshotSource
from tecc_brain.market.base import MarketDataSource
from tecc_brain.models import (
    AutonomyMode,
    BrainProfile,
    Decision,
    ExecutionIntent,
    Mandate,
    MarketSnapshot,
    Portfolio,
    RiskTier,
    VaultState,
    usd_to_onchain,
)
from tecc_brain.reference import Reference, load_reference
from tecc_brain.strategy.market_view import ClusterStatus, MarketView, assess_market
from tecc_brain.strategy.planner import (
    OptionsAssessment,
    assess_options,
    decide,
    load_demo_profile,
    soft_limit,
)
from tecc_brain.strategy.portfolio import load_demo_portfolio

AGENT_ORDER = (
    "gatekeeper_intake",
    "profile",
    "nlp_sentinel",
    "econometric_liquidity",
    "gatekeeper_aggregator",
    "brain",
    "web3_executor",
)
AGENT_TITLES = {
    "gatekeeper_intake": "Gatekeeper · intake (prompt-injection defence)",
    "profile": "Profile (learned user model)",
    "nlp_sentinel": "NLP Risk Sentinel",
    "econometric_liquidity": "Econometric & Liquidity agent",
    "gatekeeper_aggregator": "Gatekeeper · aggregator",
    "brain": "AI Brain (single-pass synthesis)",
    "web3_executor": "Web3 Executor",
}
DEMO_ACCOUNT = "demo"
Status = Literal["refused", "unparsed", "blocked", "decided"]


class AgentReport(BaseModel):
    agent: str
    title: str
    lines: list[str]


class RegimeView(BaseModel):
    symbol: str
    price: float
    fair_value: float
    p_normal: float
    p_distress: float
    p_failure: float
    regime: Literal["normal", "distress", "failure"]
    cluster: str | None


class ProfileSummary(BaseModel):
    account: str
    tier: RiskTier
    lam: float
    tau: float
    soft_limit_usd: float


class PipelineResult(BaseModel):
    status: Status
    parse: ParseOutcome
    decision: Decision | None = None
    intent: ExecutionIntent | None = None
    regimes: dict[str, RegimeView] = {}
    clusters: dict[str, ClusterStatus] = {}
    profile: ProfileSummary | None = None
    brain_report: BrainReport | None = None  # the single, validated decision record (None if refused/unparsed)
    agents: list[AgentReport] = []


class Executor(Protocol):
    """Phase 7 plugs a real signer/sender in here."""

    def submit(self, intent: ExecutionIntent, account: str) -> ExecutionIntent: ...


@dataclass
class BrainDeps:
    market: MarketDataSource = field(default_factory=lambda: SnapshotSource("demo"))
    store: ProfileStore = field(default_factory=ProfileStore)
    vault: VaultState = field(default_factory=lambda: VaultState(tether_radius_usd=500.0))
    portfolio: Portfolio | None = None
    parser: IntentParser = field(default_factory=default_parser)
    ref: Reference = field(default_factory=load_reference)
    executor: Executor | None = None
    news_hook: Callable[[MarketSnapshot], MarketSnapshot] | None = None  # e.g. Member 4's FinBERT feed
    brain_llm: BrainLLM | None = None  # None → the rule-based decision is the BrainReport (offline demo)
    brain_timeout_s: float = BRAIN_TIMEOUT_S


class BrainState(TypedDict, total=False):
    text: str
    account: str
    mandate_in: Mandate | None  # an order the user already confirmed (/api/mandate/confirm): re-scanned, never re-parsed
    status: Status
    parse: ParseOutcome
    profile: BrainProfile
    portfolio: Portfolio
    snapshot: MarketSnapshot
    view: MarketView
    assessment: OptionsAssessment
    decision: Decision
    brain_report: BrainReport
    intent: ExecutionIntent | None
    agents: Annotated[list[AgentReport], operator.add]


def _report(agent: str, lines: list[str]) -> list[AgentReport]:
    return [AgentReport(agent=agent, title=AGENT_TITLES[agent], lines=lines)]


def regime_label(p_normal: float, p_distress: float, p_failure: float) -> Literal["normal", "distress", "failure"]:
    return max((("normal", p_normal), ("distress", p_distress), ("failure", p_failure)), key=lambda kv: kv[1])[0]  # type: ignore[return-value]


def load_or_create_profile(store: ProfileStore, account: str) -> BrainProfile:
    profile = store.load(account)
    if profile is None:
        profile = load_demo_profile() if account == DEMO_ACCOUNT else new_profile(account, RiskTier.BALANCED)
        store.save(profile)
    return profile


def build_graph(deps: BrainDeps | None = None) -> Any:
    deps = deps or BrainDeps()

    def gatekeeper_intake(state: BrainState) -> dict[str, Any]:
        portfolio = deps.portfolio or (
            load_demo_portfolio() if state["account"] == DEMO_ACCOUNT else Portfolio(account=state["account"])
        )
        confirmed = state.get("mandate_in")
        if confirmed is not None:
            # The user approved this exact structured order. Parsing again could change it (an LLM parser is not
            # deterministic, and profile constraints added at /draft are not in the text), so only the firewall
            # re-runs here, as defence in depth.
            outcome = ParseOutcome(mandate=confirmed, verdict=scan(confirmed.raw_text))
            if not outcome.verdict.allowed:
                outcome.mandate = None
        else:
            outcome = deps.parser.parse(state["text"], deps.ref, portfolio)
        lines: list[str] = []
        if not outcome.verdict.allowed:
            threats = ", ".join(t.value for t in outcome.verdict.threats)
            lines.append(f"Refused: the request contains instructions the Brain never follows ({threats}).")
            return {"status": "refused", "parse": outcome, "portfolio": portfolio, "agents": _report("gatekeeper_intake", lines)}
        lines.append("Firewall: no injected instructions found.")
        masked, _ = mask(outcome.verdict.normalized)
        lines.append(f"Privacy sieve: a cloud model would only see “{masked}”.")
        if outcome.mandate is None:
            lines.append(f"Could not understand the request: {'; '.join(outcome.errors) or 'no action found'}.")
            return {"status": "unparsed", "parse": outcome, "portfolio": portfolio, "agents": _report("gatekeeper_intake", lines)}
        m = outcome.mandate
        how = "Confirmed by you" if confirmed is not None else f"Understood ({m.parser} parser)"
        lines.append(f"{how}: {m.action.value} {m.amount:g} {m.asset}, horizon {m.horizon_days} days"
                     + (f", constraints {', '.join(m.constraints)}" if m.constraints else "") + ".")
        return {"parse": outcome, "portfolio": portfolio, "agents": _report("gatekeeper_intake", lines)}

    def profile(state: BrainState) -> dict[str, Any]:
        p = load_or_create_profile(deps.store, state["account"])
        used = [v for v in p.approvals if p.has_history(v)]
        lines = [
            f"{p.tier.name.title()} tier · loss aversion λ {p.lam:.2f} · trust τ {p.tau:.2f}.",
            f"Learned history on {len(used)} venue(s)" + (f": {', '.join(sorted(used))}." if used else "."),
        ]
        disliked = sorted({pref.protocol for pref in p.preferences if pref.protocol and pref.polarity < 0})
        if disliked:
            lines.append(f"You asked to avoid: {', '.join(disliked)}.")
        return {"profile": p, "agents": _report("profile", lines)}

    def nlp_sentinel(state: BrainState) -> dict[str, Any]:
        snapshot = deps.market.snapshot()
        if deps.news_hook is not None:
            snapshot = deps.news_hook(snapshot)
        view = assess_market(snapshot, deps.ref)
        lines = [f"Market data: {snapshot.source} as of {snapshot.as_of:%Y-%m-%d %H:%M} UTC; 1Y Shibor hurdle {snapshot.hurdle_rate * 100:.2f}%."]
        worst = sorted(snapshot.news, key=lambda n: n.p_negative, reverse=True)[:3]
        lines += [f"News: “{n.headline}” → {n.p_negative:.0%} negative for {n.entity}." for n in worst]
        for symbol, a in sorted(view.assessments.items()):
            label = regime_label(a.probs.p_normal, a.probs.p_distress, a.probs.p_failure)
            if label != "normal" or a.gap > 0.005:
                lines.append(
                    f"{symbol} at {a.price:.3f} vs fair value {a.fair_value:.3f}: {label} "
                    f"(normal {a.probs.p_normal:.0%} · temporary distress {a.probs.p_distress:.0%} · failure {a.probs.p_failure:.0%})."
                )
        stressed = [c for c in view.clusters.values() if c.stressed]
        lines += [f"Cluster {c.cluster} under stress (worst: {c.worst_member}); failing: {', '.join(c.failing) or 'none'}." for c in stressed]
        if len(lines) == 1 + len(worst):
            lines.append("All pegs normal; no cluster under stress.")
        return {"snapshot": snapshot, "view": view, "agents": _report("nlp_sentinel", lines)}

    def econometric_liquidity(state: BrainState) -> dict[str, Any]:
        m = state["parse"].mandate
        assert m is not None
        assessment = assess_options(m, state["snapshot"], state["profile"], deps.vault, deps.ref, view=state["view"])
        lines = list(assessment.trace)
        for venue, cand in assessment.passing:
            s = cand.score
            if s is not None and s.cvar_95 is not None:
                sharpe = f"{s.sharpe:.2f}" if s.sharpe is not None else "n/a"
                lines.append(f"{venue.id}: Sharpe {sharpe} · CVaR95 {s.cvar_95 * 100:.1f}% · depth ${state['snapshot'].venues[venue.id].depth_usd:,.0f}.")
        return {"assessment": assessment, "agents": _report("econometric_liquidity", lines)}

    def gatekeeper_aggregator(state: BrainState) -> dict[str, Any]:
        assessment = state["assessment"]
        decision = decide(assessment, state["snapshot"], state["portfolio"], state["profile"], deps.vault, deps.ref)
        lines = decision.trace[len(assessment.trace):]
        return {"decision": decision, "agents": _report("gatekeeper_aggregator", lines)}

    def brain(state: BrainState) -> dict[str, Any]:
        baseline = state["decision"]
        payload = build_brain_input(baseline, state["assessment"].amount_usd, state["profile"], deps.vault,
                                    state["snapshot"], state["view"], deps.ref)
        decision, report = synthesize(baseline, payload, deps.brain_llm, deps.brain_timeout_s)
        lines = [f"Decision {report.decision} by the {'AI model' if report.producer == 'llm' else 'rule-based gatekeeper'}"
                 + (f" (model output not used: {report.fallback_reason})" if report.fallback_reason else "") + "."]
        lines.append(report.user_explanation)
        intent = None
        auto = next((c for c in decision.cards if c.mode == AutonomyMode.AUTO), None)
        if auto is not None and decision.auto_amount_usd > 0:
            venue = deps.ref.venues[auto.candidate.venue_id]
            intent = ExecutionIntent(
                card_label=auto.label, venue_id=venue.id, action=venue.action, asset_in=auto.candidate.asset_in,
                amount_usd=decision.auto_amount_usd, amount_onchain=usd_to_onchain(decision.auto_amount_usd),
                target_address=venue.target_address, market=auto.market,
            )
            lines.append(f"Execution intent: {venue.action.value} ${intent.amount_usd:,.0f} into {venue.name} "
                         f"({intent.amount_onchain} on-chain units).")
        status: Status = "blocked" if decision.mode == AutonomyMode.BLOCKED else "decided"
        return {"decision": decision, "brain_report": report, "intent": intent, "status": status,
                "agents": _report("brain", lines)}

    def web3_executor(state: BrainState) -> dict[str, Any]:
        intent = state.get("intent")
        if intent is None:
            return {"agents": _report("web3_executor", ["Nothing runs automatically: waiting for your choice."])}
        if deps.executor is None:
            lines = ["Prepared, not sent: on-chain signing with the session key arrives with the vault deployment."]
            return {"intent": intent, "agents": _report("web3_executor", lines)}
        sent = deps.executor.submit(intent, state["account"])
        lines = [f"{sent.status}: {sent.detail or sent.tx_hash or ''}".strip()]
        if sent.tx_hash and sent.detail:
            lines.append(f"On-chain tx: {sent.tx_hash}")
        return {"intent": sent, "agents": _report("web3_executor", lines)}

    def after_intake(state: BrainState) -> str:
        return END if state.get("status") in ("refused", "unparsed") else "profile"

    def after_brain(state: BrainState) -> str:
        return END if state.get("status") == "blocked" else "web3_executor"

    graph = StateGraph(BrainState)
    for name, fn in (
        ("gatekeeper_intake", gatekeeper_intake),
        ("profile", profile),
        ("nlp_sentinel", nlp_sentinel),
        ("econometric_liquidity", econometric_liquidity),
        ("gatekeeper_aggregator", gatekeeper_aggregator),
        ("brain", brain),
        ("web3_executor", web3_executor),
    ):
        graph.add_node(name, fn)
    graph.add_edge(START, "gatekeeper_intake")
    graph.add_conditional_edges("gatekeeper_intake", after_intake, ["profile", END])
    graph.add_edge("profile", "nlp_sentinel")
    graph.add_edge("nlp_sentinel", "econometric_liquidity")
    graph.add_edge("econometric_liquidity", "gatekeeper_aggregator")
    graph.add_edge("gatekeeper_aggregator", "brain")
    graph.add_conditional_edges("brain", after_brain, ["web3_executor", END])
    graph.add_edge("web3_executor", END)
    return graph.compile()


def regime_views(view: MarketView, ref: Reference) -> dict[str, RegimeView]:
    out: dict[str, RegimeView] = {}
    for symbol, a in view.assessments.items():
        p = a.probs
        out[symbol] = RegimeView(
            symbol=symbol, price=a.price, fair_value=a.fair_value, p_normal=p.p_normal, p_distress=p.p_distress,
            p_failure=p.p_failure, regime=regime_label(p.p_normal, p.p_distress, p.p_failure),
            cluster=ref.assets[symbol].cluster,
        )
    return out


def run_pipeline(text: str, account: str, mandate: Mandate | None = None, **deps: Any) -> PipelineResult:
    """`mandate`: a confirmed order from the /draft → /confirm loop; when set, `text` is ignored for parsing."""
    brain = BrainDeps(**deps)
    initial: BrainState = {"text": mandate.raw_text if mandate is not None else text, "account": account,
                           "mandate_in": mandate, "agents": []}
    state: BrainState = build_graph(brain).invoke(initial)
    view = state.get("view")
    regimes = regime_views(view, brain.ref) if view is not None else {}
    profile = state.get("profile")
    return PipelineResult(
        status=state.get("status", "decided"),
        parse=state["parse"],
        decision=state.get("decision"),
        intent=state.get("intent"),
        regimes=regimes,
        brain_report=state.get("brain_report"),
        clusters=view.clusters if view is not None else {},
        profile=ProfileSummary(
            account=profile.account, tier=profile.tier, lam=profile.lam, tau=profile.tau,
            soft_limit_usd=soft_limit(profile, brain.vault),
        ) if profile is not None else None,
        agents=state.get("agents", []),
    )


__all__ = [
    "AGENT_ORDER", "AGENT_TITLES", "AgentReport", "BrainDeps", "Executor", "PipelineResult", "ProfileSummary",
    "RegimeView", "build_graph", "load_or_create_profile", "regime_label", "regime_views", "run_pipeline",
]

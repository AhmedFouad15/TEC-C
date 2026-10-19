"""Regression tests for the System Flow Audit findings (B1–B5, N1–N7): each test pins one gap shut."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from tecc_brain.api.deps import ProposalCache, get_anchors, get_brain_llm, get_proposals, get_store
from tecc_brain.app import app
from tecc_brain.graph.brain import SCHEMA_VERSION
from tecc_brain.graph.pipeline import load_or_create_profile
from tecc_brain.models import ActionType, CardLabel, ExecutionIntent, NotePreference, usd_to_onchain
from tecc_brain.onchain.anchoring import AuditAnchorService
from tecc_brain.onchain.audit_anchor import AuditRecordType
from tecc_brain.onchain.executor import MarketRouter


class MemStore:
    def __init__(self):
        self.d = {}

    def load(self, account):
        return self.d.get(account.lower())

    def save(self, profile):
        self.d[profile.account.lower()] = profile


@pytest.fixture
def store():
    return MemStore()


@pytest.fixture
def api(store):
    proposals = ProposalCache()
    llm_box = {"llm": None}
    app.dependency_overrides.update({get_store: lambda: store, get_proposals: lambda: proposals,
                                     get_brain_llm: lambda: llm_box["llm"]})
    client = TestClient(app)
    client.llm = llm_box
    yield client
    for dep in (get_store, get_proposals, get_brain_llm):
        app.dependency_overrides.pop(dep, None)


def model(edit):
    """A fake cloud model answering in privacy units (amount_unit) with a valid verdict the test then bends."""
    def complete(system, payload):
        p = json.loads(payload)
        v = {"schema_version": SCHEMA_VERSION, "request_id": p["request_id"], "amount_unit": "privacy_units",
             "decision": "PROPOSE", "allocations": [], "total_auto_usd": 0.0, "reason_codes": [],
             "vetoes_honored": [x["id"] for x in p["vetoes"]], "signal_conflicts": [], "confidence": 0.5,
             "user_explanation": "ok"}
        return json.dumps(edit(v, p))
    return complete


def keep_others(v, p, target_venue, mode):
    """Set one venue's card to `mode`; every other card keeps what the rules allowed."""
    allocs = []
    for c in p["candidates"]:
        if c["venue_id"] == target_venue:
            allocs.append({"candidate_id": c["id"], "amount_usd": 0.0 if mode == "BLOCKED" else c["max_amount_usd"], "mode": mode})
        else:
            allocs.append({"candidate_id": c["id"], "amount_usd": c["max_amount_usd"], "mode": c["allowed_mode"]})
    v["allocations"] = allocs
    v["total_auto_usd"] = sum(a["amount_usd"] for a in allocs if a["mode"] == "AUTO")
    v["decision"] = "EXECUTE" if v["total_auto_usd"] > 0 else "PROPOSE"
    return v


# --- B1 / B2: the Brain's per-card verdict is binding at /execute ------------------------------------------


def test_b1_an_ai_vetoed_card_cannot_be_executed_but_others_can(api):
    api.llm["llm"] = model(lambda v, p: keep_others(v, p, "aave_v3_usdc", "BLOCKED"))
    body = api.post("/api/mandate/propose", json={"text": "Optimize my $300 USDC"}).json()
    vetoed = next(c for c in body["decision"]["cards"] if c["candidate"]["venue_id"] == "aave_v3_usdc")
    assert vetoed["mode"] == "BLOCKED"
    r = api.post("/api/mandate/execute", json={"proposal_id": body["proposal_id"], "label": vetoed["label"],
                                               "venue_id": "aave_v3_usdc"})
    assert r.status_code == 409 and "vetoed" in r.json()["detail"]
    other = next(c for c in body["decision"]["cards"] if c["mode"] != "BLOCKED")
    r = api.post("/api/mandate/execute", json={"proposal_id": body["proposal_id"], "label": other["label"],
                                               "venue_id": other["candidate"]["venue_id"]})
    assert r.status_code == 200  # the veto did not burn the proposal


def test_b2_ai_breakout_requires_faceid_even_inside_the_radius(api, _simulated_markets_only):
    def breakout_aave(v, p):
        aave = next(c for c in p["candidates"] if c["venue_id"] == "aave_v3_usdc")
        v["allocations"] = [{"candidate_id": aave["id"], "amount_usd": aave["max_amount_usd"], "mode": "BREAKOUT"}]
        return v

    api.llm["llm"] = model(breakout_aave)
    body = api.post("/api/mandate/propose", json={"text": "Optimize my $300 USDC"}).json()
    card = next(c for c in body["decision"]["cards"] if c["candidate"]["venue_id"] == "aave_v3_usdc")
    assert card["mode"] == "BREAKOUT" and card["candidate"]["amount_usd"] <= 500  # inside the radius
    out = api.post("/api/mandate/execute", json={"proposal_id": body["proposal_id"], "label": card["label"],
                                                 "venue_id": "aave_v3_usdc"}).json()
    assert out["intent"]["status"] == "breakout_required" and "FaceID" in out["message"]
    assert out["intent"]["tx_hash"] is None and _simulated_markets_only.tether_tracker.get_spent("demo") == 0


# --- B3: PegGuard trades go through the soft tether, the Brain and the router ---------------------------


def _arbitrage(api, **body):
    api.post("/api/arbitrage/toggle", json={"account": "demo", "enabled": True})
    return api.post("/api/arbitrage/scan", json={"account": "demo", **body}).json()


def test_b3_a_client_priced_million_dollar_scan_runs_at_most_the_soft_tether(api):
    report = _arbitrage(api, order_size_usd=1_000_000, symbols=["USDC", "DAI", "FRAX"],
                        price_overrides={"USDC": 0.90, "DAI": 0.95, "FRAX": 0.94})
    ran = [o["execution_intent"]["amount_usd"] for o in report["outcomes"] if o["status"] == "executed"]
    assert sum(ran) <= 400.0 + 1e-6  # (0.5 + 0.5·τ) × $500 radius — never $1.47M
    assert report["held_count"] >= 2 and report["proposal_id"]
    assert report["brain_report"]["producer"] == "rules"
    assert all(o["execution_intent"]["market"] == "arbitrage" for o in report["outcomes"] if o["status"] == "executed")


def test_b3_every_executed_trade_goes_through_the_router(api, _simulated_markets_only):
    calls = []
    original = _simulated_markets_only.submit

    def spy(intent, account, market=None, limit_usd=None):
        calls.append((intent.asset_in, intent.amount_usd, market, limit_usd))
        return original(intent, account, market=market, limit_usd=limit_usd)

    _simulated_markets_only.submit = spy
    report = _arbitrage(api, order_size_usd=250, symbols=["USDC"], price_overrides={"USDC": 0.97})
    assert report["executed_count"] == 1
    assert calls == [("USDC", pytest.approx(calls[0][1]), "arbitrage", 500.0)]


def test_b3_the_ai_brain_can_veto_an_authorized_arbitrage_trade(api):
    def veto_all(v, p):
        v["allocations"] = [{"candidate_id": c["id"], "amount_usd": 0.0, "mode": "BLOCKED"} for c in p["candidates"]]
        v["decision"] = "PROPOSE"
        return v

    api.llm["llm"] = model(veto_all)
    report = _arbitrage(api, order_size_usd=250, symbols=["USDC"], price_overrides={"USDC": 0.97})
    assert [o["status"] for o in report["outcomes"]] == ["vetoed_by_brain"]
    assert report["executed_count"] == 0 and report["brain_report"]["producer"] == "llm"


def test_b3_a_held_arbitrage_trade_can_be_approved_by_hand(api):
    report = _arbitrage(api, order_size_usd=1000, symbols=["USDC"], price_overrides={"USDC": 0.97})
    held = next(o for o in report["outcomes"] if o["status"] in ("executed", "held_for_approval"))
    r = api.post("/api/mandate/execute", json={"proposal_id": report["proposal_id"], "label": "OPPORTUNITY",
                                               "venue_id": held["execution_intent"]["venue_id"] if held["execution_intent"]
                                               else None})
    assert r.status_code == 200, r.text
    assert r.json()["intent"]["market"] == "arbitrage"


# --- B4: a model that does not answer means HOLD -----------------------------------------------------


def test_b4_model_timeout_holds_nothing_runs_automatically(api):
    def timed_out(system, payload):
        raise TimeoutError("no answer within 8.0 s")

    api.llm["llm"] = timed_out
    body = api.post("/api/mandate/propose", json={"text": "Optimize my $1,500 USDC"}).json()
    r = body["brain_report"]
    assert r["decision"] == "HOLD" and r["producer"] == "rules" and "model call failed" in r["fallback_reason"]
    assert r["reason_codes"] == ["MODEL_UNAVAILABLE"] and r["total_auto_usd"] == 0
    assert body["decision"]["mode"] == "PROPOSE" and body["decision"]["auto_amount_usd"] == 0 and body["intent"] is None
    assert body["proposal_id"]  # every option stays available for a manual approval


def test_b4_the_real_timeout_path_also_holds():
    from tecc_brain.graph.brain import synthesize
    from tecc_brain.graph.pipeline import run_pipeline
    from tecc_brain.market import SnapshotSource

    baseline = run_pipeline("Optimize my $1,500 USDC", "demo", market=SnapshotSource("demo"), store=MemStore())
    payload = {"request_id": "r1", "vetoes": [], "candidates": [], "mandate": {"amount_usd": 1500.0},
               "limits": {"vault_radius_remaining_usd": 500, "soft_limit_usd": 400, "baseline_auto_usd": 400}}

    def slow(system, user):
        time.sleep(0.5)
        return "{}"

    final, report = synthesize(baseline.decision, payload, slow, timeout_s=0.05)
    assert report.decision == "HOLD" and final.auto_amount_usd == 0
    assert all(c.mode != "AUTO" for c in final.cards)


def test_b4_a_provider_error_holds_the_options_list_too(api):
    def down(system, payload):
        raise ConnectionError("provider down")

    api.llm["llm"] = down
    body = api.post("/evaluate_options", json={"options": [
        {"option_id": "a", "action": "deposit", "asset": "USDC", "amount_usd": 150},
        {"option_id": "b", "action": "deposit", "asset": "USDC", "amount_usd": 150}]}).json()
    assert body["brain_report"]["decision"] == "HOLD" and body["status"] == "REJECT_ALL" and body["intents"] == []
    assert {r["mode"] for r in body["results"]} == {"PROPOSE"} and body["proposal_id"]


def test_b4_no_model_configured_keeps_the_offline_rules_demo(api):
    body = api.post("/api/mandate/propose", json={"text": "Optimize my $1,500 USDC"}).json()
    assert body["brain_report"]["decision"] == "EXECUTE" and body["decision"]["auto_amount_usd"] == pytest.approx(400)


# --- N1: options can be approved by hand --------------------------------------------------------------


def test_n1_options_proposal_can_be_approved_per_option(api):
    body = api.post("/evaluate_options", json={"options": [
        {"option_id": "eth", "action": "stake", "asset": "ETH", "amount_usd": 300},  # first use of Lido: held
        {"option_id": "aave", "action": "deposit", "asset": "USDC", "amount_usd": 150, "venue_id": "aave_v3_usdc"}]}).json()
    assert body["proposal_id"]
    modes = {r["option_id"]: r["mode"] for r in body["results"]}
    pending = next(oid for oid, m in modes.items() if m in ("PROPOSE", "BREAKOUT"))
    r = api.post("/api/mandate/execute", json={"proposal_id": body["proposal_id"], "label": "BEST", "option_id": pending})
    assert r.status_code == 200, r.text


def test_n1_same_venue_options_are_told_apart_by_option_id(api):
    body = api.post("/evaluate_options", json={"options": [
        {"option_id": "a", "action": "deposit", "asset": "USDC", "amount_usd": 450},
        {"option_id": "b", "action": "deposit", "asset": "USDC", "amount_usd": 450}]}).json()
    assert {r["venue_id"] for r in body["results"]} == {"aave_v3_usdc"}
    ran = {r["option_id"]: r["allocated_usd"] for r in body["results"]}
    r = api.post("/api/mandate/execute", json={"proposal_id": body["proposal_id"], "label": "BEST", "option_id": "a"})
    assert r.status_code == 200, r.text
    assert r.json()["intent"]["amount_usd"] == pytest.approx(450 - ran["a"])  # only what did not already run


# --- N2 / N6: the Brain sets the market and execution goes through the router ---------------------------


@pytest.mark.parametrize(("text", "venue", "market"), [
    ("Deposit 300 USDC into paxos", "paxg_hold", "commodities"),  # Arbitrum One
    ("Put 200 USDC into shibor_mmf", "shibor_mmf", "chinese_market"),  # FISCO BCOS
])
def test_n2_market_follows_the_venue_through_execution(api, text, venue, market):
    body = api.post("/api/mandate/propose", json={"text": text}).json()
    card = next(c for c in body["decision"]["cards"] if c["candidate"]["venue_id"] == venue)
    assert card["market"] == market
    out = api.post("/api/mandate/execute", json={"proposal_id": body["proposal_id"], "label": card["label"],
                                                 "venue_id": venue}).json()
    assert out["intent"]["market"] == market and out["intent"]["status"] == "simulated"


def test_n2_propose_routes_its_automatic_slice(api):
    propose = api.post("/api/mandate/propose", json={"text": "Optimize my $1,500 USDC"}).json()
    assert propose["intent"]["market"] == "crypto" and propose["intent"]["status"] == "simulated"


def test_n2_router_without_a_live_ethereum_vault_simulates_instead_of_crashing():
    intent = ExecutionIntent(card_label=CardLabel.BEST, venue_id="aave_v3_usdc", action=ActionType.DEPOSIT,
                             asset_in="USDC", amount_usd=100, amount_onchain=usd_to_onchain(100))
    out = MarketRouter().submit(intent, "demo")
    assert out.status == "simulated" and out.tx_hash is None and out.market == "crypto"


def test_n6_router_meters_what_actually_ran_after_a_slippage_recovery():
    class HalvingCrypto:
        def submit(self, intent, account):  # what ChainExecutor returns after a Q*/2 slippage recovery
            half = intent.amount_usd / 2
            return intent.model_copy(update={"status": "submitted", "tx_hash": "0x" + "1" * 64, "amount_usd": half,
                                             "amount_onchain": usd_to_onchain(half), "recovery_attempted": True})

    router = MarketRouter(crypto=HalvingCrypto())
    intent = ExecutionIntent(card_label=CardLabel.BEST, venue_id="aave_v3_usdc", action=ActionType.DEPOSIT,
                             asset_in="USDC", amount_usd=300, amount_onchain=usd_to_onchain(300))
    out = router.submit(intent, "demo")
    assert out.recovery_attempted and router.tether_tracker.get_spent("demo") == pytest.approx(150)


# --- N3: the user's private notes are masked before the cloud model ----------------------------------


def test_n3_quoted_notes_are_masked_in_the_cloud_payload(api, store):
    profile = load_or_create_profile(store, "demo")
    store.save(profile.model_copy(update={"preferences": [
        NotePreference(protocol="shibor_mmf", polarity=-1, quote="never again, I lost $4,250 there last year")]}))
    seen = []
    api.llm["llm"] = lambda system, payload: seen.append(payload) or "{}"
    api.post("/api/mandate/propose", json={"text": "Optimize my $1,500 USDC"})
    blockers = [b for c in json.loads(seen[0])["candidates"] for b in c["blockers"]]
    assert any("<AMT_" in b for b in blockers) and not any("4,250" in b or "4250" in b for b in blockers)


# --- N5: audit hashes are anchored (or honestly reported as not anchored) --------------------------------


class FakeAnchorClient:
    def __init__(self):
        self.anchored = []

    def anchor_record(self, record_hash, record_type):
        self.anchored.append((record_hash, AuditRecordType(record_type)))
        return "0x" + "a" * 64


def test_n5_review_notes_report_their_anchor(api):
    event = {"event_id": "note-1", "signal": "note", "at": "2026-10-18T09:00:00Z", "note": "too risky for me"}
    out = api.post("/api/review/sync", json={"account": "demo", "events": [event]}).json()
    item = out["results"][0]
    assert item["audit_record_hash"].startswith("0x") and item["audit_anchor"]["status"] == "not_configured"

    client = FakeAnchorClient()
    app.dependency_overrides[get_anchors] = lambda: AuditAnchorService(client)
    event2 = {**event, "event_id": "note-2"}
    item = api.post("/api/review/sync", json={"account": "demo", "events": [event2]}).json()["results"][0]
    assert item["audit_anchor"]["status"] == "anchored" and client.anchored[0][1] == AuditRecordType.MORNING_REVIEW_NOTE


def test_n5_submitted_arbitrage_is_anchored_by_the_router():
    class LiveArb:
        market_inputs: dict = {}

        def submit(self, intent, account):
            return intent.model_copy(update={"status": "submitted", "tx_hash": "0x" + "2" * 64,
                                             "audit_record_hash": "0x" + "3" * 64})

    client = FakeAnchorClient()
    router = MarketRouter(arbitrage=LiveArb(), anchors=AuditAnchorService(client))
    intent = ExecutionIntent(card_label=CardLabel.OPPORTUNITY, venue_id="curve_3pool", action=ActionType.BUY_DISCOUNT,
                             asset_in="USDC", amount_usd=100, amount_onchain=usd_to_onchain(100), market="arbitrage")
    out = router.submit(intent, "demo")
    assert out.audit_anchor_tx == "0x" + "a" * 64 and client.anchored == [("0x" + "3" * 64, AuditRecordType.ARBITRAGE_EXECUTED)]


def test_n5_caller_supplied_prices_are_never_anchored_as_market_depegs(api):
    client = FakeAnchorClient()
    app.dependency_overrides[get_anchors] = lambda: AuditAnchorService(client)
    _arbitrage(api, order_size_usd=250, symbols=["USDC"], price_overrides={"USDC": 0.999})
    assert all(t != AuditRecordType.DEPEG_DETECTED for _, t in client.anchored)


# --- N7: the phone gateway shows real state and runs real actions -----------------------------------------


def test_n7_gateway_state_and_actions_are_live(api):
    from tecc_brain.virtual_session import gateway

    api.post("/api/arbitrage/toggle", json={"account": "demo", "enabled": False})
    assert gateway._wallet_state()["scanner_active"] is False
    gateway.TRADE_ACTIONS["arbitrage/toggle"]({"enabled": True})
    state = gateway._wallet_state()
    assert state["scanner_active"] is True and state["monitored_assets_count"] == 25
    assert state["positions"] and state["radius_usd"] == 500.0

    body = api.post("/api/mandate/propose", json={"text": "Deposit 450 USDC into Aave"}).json()
    out = gateway.TRADE_ACTIONS["execute"]({"proposal_id": body["proposal_id"], "label": "BEST"})
    assert out["status"] == "simulated" and out["result"]["intent"]["amount_usd"] == pytest.approx(50)

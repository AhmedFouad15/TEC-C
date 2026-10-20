"""Coverage: the HTTP API's happy paths. Every test runs on an isolated profile store, fresh caches and a simulated
market router, so nothing here touches a chain or a developer's running stack."""

import itertools

import pytest
from fastapi.testclient import TestClient

from tecc_brain.api.deps import (
    DraftCache, ProposalCache, RateLimiter, get_brain_llm, get_drafts, get_limiter, get_proposals, get_router, get_store,
)
from tecc_brain.app import app
from tecc_brain.learning.onboarding import QUIZ, score_quiz
from tecc_brain.learning.store import ProfileStore
from tecc_brain.models import AutonomyMode
from tecc_brain.onchain.executor import MarketRouter
from tecc_brain.pegguard import PEGGUARD_ASSET_CATALOG
from tecc_brain.reference import load_reference
from tecc_brain.strategy.backtest import available_backtests

REF = load_reference()


@pytest.fixture
def client(tmp_path):
    store, proposals, drafts = ProfileStore(root=tmp_path / "profiles"), ProposalCache(), DraftCache()
    limiter, router = RateLimiter(), MarketRouter(daily_limit_usd=500.0)
    app.dependency_overrides.update({
        get_store: lambda: store, get_proposals: lambda: proposals, get_drafts: lambda: drafts,
        get_limiter: lambda: limiter, get_router: lambda: router, get_brain_llm: lambda: None,
    })
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["version"]


# --- catalog --------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("market", sorted({v.market for v in REF.venues.values()}))
def test_catalog_lists_every_market_with_its_venues(client, market):
    m = client.get("/api/catalog").json()["markets"][market]
    expected = {v.id for v in REF.venues.values() if v.market == market}
    assert {v["id"] for v in m["venues"]} == expected
    assert m["assets"] and m["actions"]


@pytest.mark.parametrize("venue_id", sorted(REF.venues))
def test_catalog_describes_each_venue(client, venue_id):
    markets = client.get("/api/catalog").json()["markets"]
    venue = next(v for m in markets.values() for v in m["venues"] if v["id"] == venue_id)
    ref = REF.venues[venue_id]
    assert venue["protocol"] == ref.protocol and venue["tier"] == int(ref.tier)
    assert venue["accepts"] == list(ref.accepts) and venue["action"] == ref.action.value


# --- profile and onboarding -----------------------------------------------------------------------------------------


def test_quiz_has_five_questions_with_three_options(client):
    quiz = client.get("/api/profile/quiz").json()
    assert len(quiz) == 5 and all(len(q["options"]) == 3 for q in quiz)


@pytest.mark.parametrize("account", ["demo", "alice", "bob_1", "team-lead", "0x" + "ab" * 20])
def test_a_new_account_gets_a_default_profile(client, account):
    body = client.get(f"/api/profile/{account}").json()
    assert body["account"].lower() == account.lower()
    assert body["tier"] in (1, 2, 3) and body["soft_limit_usd"] > 0
    lo, hi = body["lam_band"]
    assert lo <= body["lam"] <= hi


SAMPLE_ANSWERS = [dict(zip([q.id for q in QUIZ], combo))
                  for combo in itertools.islice(itertools.product(*[[o.id for o in q.options] for q in QUIZ]), 0, 243, 24)]


@pytest.mark.parametrize("answers", SAMPLE_ANSWERS, ids=lambda a: "-".join(a.values()))
def test_onboarding_through_the_api_matches_the_quiz_score(client, answers):
    res = client.post("/api/profile/onboard", json={"account": "onboard-user", "answers": answers, "reset": True})
    assert res.status_code == 200
    expected = score_quiz(answers)
    assert res.json()["result"]["tier"] == expected.tier
    assert res.json()["profile"]["tier"] == expected.tier


# --- market views ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", ["demo", "usdc_distress"])
def test_regime_radar_for_each_bundled_scenario(client, scenario):
    body = client.get(f"/api/risk/regimes?scenario={scenario}").json()
    assert body["source"].startswith("snapshot:") and body["hurdle_rate"] > 0
    assert body["regimes"] and body["clusters"] is not None


@pytest.mark.parametrize("symbol", ["USDC", "USDT", "DAI", "stETH", "PAXG"])
def test_headline_sandbox_scores_a_negative_headline_for_each_tracked_asset(client, symbol):
    body = client.post("/api/sentinel/headline",
                       json={"headline": f"{symbol} exploit: withdrawals paused as {symbol} de-pegs"}).json()
    assert body["signal"]["symbol"] == symbol
    assert body["signal"]["p_negative"] > 0.5
    assert body["before"] and body["after"]


def test_the_backtest_list_is_not_empty(client):
    assert client.get("/api/backtest").json()


@pytest.mark.parametrize("episode", available_backtests())
def test_every_listed_backtest_episode_runs(client, episode):
    res = client.post(f"/api/backtest/{episode}")
    assert res.status_code == 200 and res.json()


# --- free-text parsing ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("text,action,asset", [
    ("deposit 100 USDC", "deposit", "USDC"),
    ("stake 2 ETH", "stake", "ETH"),
    ("withdraw 50 USDC", "withdraw", "USDC"),
    ("grow 300 USDT", "optimize_yield", "USDT"),
    ("lend 20 DAI for a month", "deposit", "DAI"),
    ("deposit $250", "deposit", "USDC"),
    ("stake 1 stETH", "stake", "stETH"),
    ("deposit 2 gold", "deposit", "PAXG"),
])
def test_parse_endpoint(client, text, action, asset):
    body = client.post("/api/mandate/parse", json={"text": text}).json()
    assert body["verdict"]["allowed"]
    assert (body["mandate"]["action"], body["mandate"]["asset"]) == (action, asset)


# --- draft -> confirm -> propose ------------------------------------------------------------------------------------


@pytest.mark.parametrize("i,text", list(enumerate([
    "deposit 100 USDC", "deposit 250 USDC for a month", "stake 1 ETH", "lend 50 USDT", "deposit 300 USDC via aave",
])))
def test_the_draft_confirm_propose_loop(client, i, text):
    account = f"loop-{i}"
    draft = client.post("/api/mandate/draft", json={"text": text, "account": account}).json()
    assert draft["status"] == "ready" and draft["summary"]
    confirmed = client.post("/api/mandate/confirm",
                            json={"draft_id": draft["draft_id"], "version": draft["version"], "account": account})
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "confirmed"
    proposal = client.post("/api/mandate/propose", json={"draft_id": draft["draft_id"], "account": account})
    assert proposal.status_code == 200
    assert proposal.json()["decision"] is not None


@pytest.mark.parametrize("text", ["deposit 100 USDC", "deposit 2000 USDC somewhere safe for a month", "stake 1 ETH, low risk"])
def test_propose_rates_routes_for_a_free_text_order(client, text):
    body = client.post("/api/mandate/propose", json={"text": text, "account": "propose-user"}).json()
    assert body["status"] == "decided"
    assert body["decision"]["cards"]
    assert body["brain_report"]["producer"] == "rules"
    assert [a["agent"] for a in body["agents"]][0] == "gatekeeper_intake"


# --- structured options ---------------------------------------------------------------------------------------------

PINNED = [(v.id, v.action.value, asset) for v in REF.venues.values() for asset in v.accepts]


@pytest.mark.parametrize("venue_id,action,asset", PINNED)
def test_options_with_a_pinned_venue_are_evaluated(client, venue_id, action, asset):
    res = client.post("/evaluate_options", json={"account": "options-user", "options": [
        {"option_id": "A", "action": action, "asset": asset, "amount_usd": 100, "venue_id": venue_id}]})
    assert res.status_code == 200
    result = res.json()["results"][0]
    assert result["option_id"] == "A"
    assert result["mode"] in [m.value for m in AutonomyMode]
    assert res.json()["brain_report"] is not None


@pytest.mark.parametrize("action,asset", sorted({(v.action.value, a) for v in REF.venues.values() for a in v.accepts}))
def test_options_without_a_venue_let_the_brain_pick_one(client, action, asset):
    res = client.post("/evaluate_options", json={"account": "options-user", "options": [
        {"option_id": "A", "action": action, "asset": asset, "amount_usd": 100}]})
    assert res.status_code == 200
    assert res.json()["status"] in ("EXECUTE_ONE", "SPLIT", "REJECT_ALL")


def test_several_options_come_back_in_one_answer(client):
    options = [{"option_id": chr(65 + i), "action": "deposit", "asset": "USDC", "amount_usd": 50 + 10 * i} for i in range(5)]
    body = client.post("/evaluate_options", json={"account": "options-user", "options": options}).json()
    assert sorted(r["option_id"] for r in body["results"]) == ["A", "B", "C", "D", "E"]


# --- PegGuard and settings --------------------------------------------------------------------------------------------


def test_pegguard_catalog_endpoint(client):
    assert sorted(client.get("/api/arbitrage/assets").json()) == sorted(PEGGUARD_ASSET_CATALOG)


def test_pegguard_status_endpoint(client):
    body = client.get("/api/arbitrage/status?account=status-user").json()
    assert body["monitored_assets_count"] == 25 and body["enabled"] is False


def test_settings_never_return_keys(client):
    body = client.get("/api/settings").json()
    assert set(body) >= {"x_search", "sentinel", "brain", "pegguard"}
    flat = str(body)
    assert "api_key" not in flat and "xai-" not in flat and "AIza" not in flat  # never a key, only whether one is set
    assert isinstance(body["brain"]["configured"], bool) and isinstance(body["sentinel"]["configured"], bool)

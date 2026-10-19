"""/api/catalog and /api/vault/*: the dashboard reads the real vault and, on the local test chain only, performs the
owner's actions (faucet, Morning Review, radius, killswitch, biometric-gated withdraw)."""

import pytest
from eth_account import Account
from fastapi.testclient import TestClient

from tecc_brain.app import app
from tecc_brain.onchain.deploy import deploy_local
from tecc_brain.onchain.mandate import UserMandate, policy_hash
from tecc_brain.onchain.markets import MarketFile, save_market
from tecc_brain.onchain.rpc import Rpc
from tecc_brain.onchain.session import provision_session_key

client = TestClient(app)
COLD_WALLET = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"


@pytest.fixture
def no_vault(tmp_path, monkeypatch):
    monkeypatch.setenv("TECC_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("TECC_NETWORK", "anvil")


@pytest.fixture(scope="module")
def deployed(anvil_url, tmp_path_factory):
    rpc = Rpc(anvil_url)
    dep = deploy_local(rpc, eth_usd=2500.0, fund_eth_wei=10**18)
    session = Account.create()
    now = rpc.block_timestamp()
    mandate = UserMandate(account=dep.account, session_key=session.address, max_amount_usd=1000.0,
                          valid_after=now - 60, valid_until=now + 86_400, risk_tier=2,
                          policy=policy_hash(sorted(dep.venues)))
    provision_session_key(rpc, dep, mandate, fund_wei=10**17)
    state = tmp_path_factory.mktemp("state")
    return state, MarketFile(network="anvil", rpc_url=anvil_url, deployment=dep, mandate=mandate,
                             session_key="0x" + bytes(session.key).hex())


@pytest.fixture
def vault_state(deployed, monkeypatch):
    state, market = deployed
    monkeypatch.setenv("TECC_STATE_DIR", str(state))
    monkeypatch.setenv("TECC_NETWORK", "anvil")
    save_market(market)
    return market


def test_catalog_groups_venues_by_market_so_the_composer_never_offers_eth_in_china():
    markets = client.get("/api/catalog").json()["markets"]
    assert "ETH" in markets["crypto"]["assets"]
    assert "ETH" not in markets["chinese_market"]["assets"]
    assert set(markets["chinese_market"]["assets"]) <= {"USDC", "USDT"}
    assert markets["commodities"]["chain"] == "Arbitrum"


def test_without_a_deployment_the_vault_says_how_to_create_one(no_vault):
    r = client.get("/api/vault/demo")
    assert r.status_code == 404 and "dev_up.sh" in r.json()["detail"]


def test_vault_reads_the_deposit_address_balances_and_the_on_chain_leash(vault_state):
    v = client.get("/api/vault/demo").json()
    assert v["live"] and v["dev_chain"]
    assert v["deposit_address"] == vault_state.deployment.account
    assert v["policy"]["radius_usd"] == 500.0 and v["policy"]["ceiling_usd"] >= 500.0
    assert v["session_key"]["authorized"] is True
    assert any(h["symbol"] == "ETH" for h in v["holdings"])


def test_faucet_funds_the_vault_on_the_test_chain(vault_state):
    before = client.get("/api/vault/demo").json()["total_usd"]
    r = client.post("/api/vault/demo/faucet", json={"eth": 0, "usdc": 250})
    assert r.status_code == 200 and len(r.json()["tx_hashes"]) == 1
    assert client.get("/api/vault/demo").json()["total_usd"] == pytest.approx(before + 250)


def test_radius_and_killswitch_change_the_contract(vault_state):
    assert client.post("/api/vault/demo/radius", json={"radius_usd": 750}).json()["radius_usd"] == 750.0
    assert client.get("/api/vault/demo").json()["policy"]["radius_usd"] == 750.0
    assert client.post("/api/vault/demo/session", json={"authorized": False}).json()["authorized"] is False
    assert client.get("/api/vault/demo").json()["session_key"]["authorized"] is False
    client.post("/api/vault/demo/session", json={"authorized": True})
    client.post("/api/vault/demo/radius", json={"radius_usd": 500})


def test_withdraw_needs_the_biometric_window(vault_state):
    r = client.post("/api/vault/demo/withdraw", json={"to": COLD_WALLET, "asset": "ETH", "amount": 0.01})
    assert r.status_code == 403 and "passkey" in r.json()["detail"]


def test_withdraw_inside_the_biometric_window_moves_real_funds(vault_state, monkeypatch):
    from tecc_brain.api import biometrics

    monkeypatch.setattr(biometrics.get_biometric_manager(), "is_biometric_window_active", lambda account: (True, None))
    rpc = Rpc(vault_state.rpc_url)
    before = int(rpc.call("eth_getBalance", [COLD_WALLET, "latest"]), 16)
    r = client.post("/api/vault/demo/withdraw", json={"to": COLD_WALLET, "asset": "ETH", "amount": 0.01})
    assert r.status_code == 200, r.text
    assert int(rpc.call("eth_getBalance", [COLD_WALLET, "latest"]), 16) - before == 10**16


def test_owner_actions_refuse_a_non_test_chain(vault_state, monkeypatch):
    monkeypatch.setattr(Rpc, "chain_id", lambda self: 11155111)  # Sepolia: the user's device must sign there
    assert client.post("/api/vault/demo/faucet", json={}).status_code == 403
    assert client.post("/api/vault/demo/session", json={"authorized": False}).status_code == 403


# --- breakouts and record names (the dashboard's FaceID approval and the Morning Review list) ----------------

def _intent(dep, usd: float, venue: str = "aave_v3_usdc"):
    from tecc_brain.models import ActionType, CardLabel, ExecutionIntent
    from tecc_brain.onchain.executor import usd_to_onchain

    return ExecutionIntent(card_label=CardLabel.BEST, venue_id=venue, action=ActionType.DEPOSIT, asset_in="USDC",
                           amount_usd=usd, amount_onchain=usd_to_onchain(usd), market="crypto")


def _executor(market, tmp_path):
    from tecc_brain.onchain.executor import ChainExecutor, RecordLedger

    return ChainExecutor(Rpc(market.rpc_url), market.deployment, market.session_key, market.mandate,
                         RecordLedger(tmp_path / "records.json"))


def test_review_records_are_named_after_the_venue_the_brain_used(vault_state):
    from tecc_brain.onchain.markets import live_chain_executor

    client.post("/api/vault/demo/faucet", json={"eth": 0, "usdc": 2000})
    client.post("/api/vault/demo/radius", json={"radius_usd": 500})
    sent = live_chain_executor("anvil").submit(_intent(vault_state.deployment, 20.0), "demo")
    assert sent.status == "submitted", sent.detail
    reviews = client.get("/api/vault/demo").json()["pending_reviews"]
    latest = max(reviews, key=lambda r: r["id"])
    # the USDC deposit calls the token contract, yet the record says which venue it was for
    assert latest["venue_id"] == "aave_v3_usdc" and latest["tx_hash"] == sent.tx_hash


def test_over_the_leash_needs_the_owner_and_runs_once_approved(vault_state, tmp_path):
    client.post("/api/vault/demo/faucet", json={"eth": 0, "usdc": 5000})
    client.post("/api/vault/demo/radius", json={"radius_usd": 100})
    ex = _executor(vault_state, tmp_path)
    plain = ex.submit(_intent(vault_state.deployment, 900.0), "demo")
    assert plain.status == "failed" and "TetherRadiusExceeded" in plain.detail  # the leash holds for the AI alone
    approved = ex.submit(_intent(vault_state.deployment, 900.0), "demo", breakout=True)
    assert approved.status == "submitted", approved.detail  # the owner's one-time sign-approval broke it once


def test_a_breakout_on_a_real_network_waits_for_the_users_device(vault_state, tmp_path):
    ex = _executor(vault_state, tmp_path)
    ex.dep = ex.dep.model_copy(update={"chain_id": 11155111})
    assert "device" in ex._approve_breakout(b"\x00" * 4)


def test_execute_asks_for_faceid_until_a_passkey_window_is_open(vault_state, monkeypatch):
    from tecc_brain.api import biometrics

    client.post("/api/vault/demo/radius", json={"radius_usd": 100})
    p = client.post("/api/mandate/propose", json={"text": "stake 1 ETH, low risk", "account": "demo"}).json()
    card = next(c for c in p["decision"]["cards"] if c["mode"] == "BREAKOUT")
    body = {"proposal_id": p["proposal_id"], "account": "demo", "label": card["label"], "venue_id": card["candidate"]["venue_id"]}
    monkeypatch.setattr(biometrics.get_biometric_manager(), "is_biometric_window_active", lambda account: (False, None))
    first = client.post("/api/mandate/execute", json=body).json()
    assert first["intent"]["status"] == "breakout_required" and "FaceID" in first["message"]

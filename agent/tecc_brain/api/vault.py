"""/api/catalog and /api/vault/*: the dashboard's window onto the real vault.

Read side (any network with a deployed vault, see scripts/deploy_market_chain.py):
    GET  /api/catalog                    venues grouped by market (what the composer may offer)
    GET  /api/vault/{account}            deposit address, on-chain balances, positions, the TetherGuardHook policy
                                         (radius, today's spend, ceiling, tier), pending reviews, AI heartbeat

Owner side (LOCAL TEST CHAIN ONLY, chain id 31337): on Anvil the vault's root owner is an unlocked dev account,
so the Brain can submit the owner's own transactions for the demo. On a real network these are signed on the
user's device and the Brain never holds that key, so every owner route refuses to run anywhere else.
    POST /api/vault/{account}/faucet     test ETH + mint test USDC into the vault
    POST /api/vault/{account}/review     ratify / flag / note an execution record (on-chain Morning Review)
    POST /api/vault/{account}/radius     set the daily tether radius
    POST /api/vault/{account}/session    revoke (or restore) the Brain's session key: the real killswitch
    POST /api/vault/{account}/withdraw   send funds out; requires an active biometric (passkey) window
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tecc_brain.api.deps import Account, get_ref
from tecc_brain.onchain.artifacts import NATIVE_ETH, Contract, revert_reason
from tecc_brain.onchain.markets import MarketFile, load_market, _ledger
from tecc_brain.onchain.rpc import Rpc, RpcError
from tecc_brain.onchain.session import MODULE_TYPE_EXECUTOR, execution_calldata, provision_session_key
from tecc_brain.models import VaultState
from tecc_brain.reference import Reference

router = APIRouter(tags=["vault"])

DEV_CHAIN_ID = 31337
USD8 = 10**8  # the hook meters everything in 8-decimal USD
USDC6 = 10**6
MARKET_LABEL = {"crypto": "Crypto", "chinese_market": "Chinese market", "commodities": "Commodities", "arbitrage": "Arbitrage"}
MARKET_CHAIN = {"crypto": "Ethereum", "chinese_market": "FISCO BCOS", "commodities": "Arbitrum", "arbitrage": "PegGuard"}
REVIEW_STATUS = {0: "pending", 1: "ratified", 2: "flagged", 3: "noted"}


def _owner_key(owner: str = "") -> str | None:
    key = os.environ.get("TECC_DEPLOYER_KEY")
    if key and not key.startswith("your_") and not key.startswith("0x..."):
        return key
    for p in (
        Path(__file__).resolve().parents[2] / ".state" / "wallet.json",
        Path(__file__).resolve().parents[3] / ".state" / "wallet.json",
    ):
        if p.exists():
            try:
                wdata = json.loads(p.read_text(encoding="utf-8"))
                if not owner or wdata.get("address", "").lower() == owner.lower():
                    return wdata.get("private_key")
            except Exception:
                pass
    return None


def _network() -> str:
    return os.environ.get("TECC_NETWORK", "anvil")


def _active_market() -> MarketFile | None:
    net = _network()
    market = load_market(net)
    if market is not None:
        return market
    # Fall back to any active deployed market so the dashboard displays live on-chain status
    for candidate in ("arbitrum", "sepolia", "fisco_bcos", "anvil"):
        m = load_market(candidate)
        if m is not None:
            return m
    return None


def _vault(account: str) -> tuple[MarketFile, Rpc]:
    """The deployed vault behind this account. One local deployment serves the demo account."""
    market = _active_market()
    if market is None:
        raise HTTPException(404, f"no vault deployed on {_network()}: run ./dev_up.sh (or scripts/deploy_market_chain.py)")
    rpc = Rpc(market.rpc_url, timeout_s=5)
    try:
        code = rpc.call("eth_getCode", [market.deployment.account, "latest"])
    except Exception as exc:  # node down
        raise HTTPException(503, f"chain node not reachable at {market.rpc_url}: {exc}") from exc
    if code in ("0x", "0x0", None):
        raise HTTPException(409, "the vault is not on this chain any more (was the node restarted?): run ./dev_up.sh")
    return market, rpc


def _dev_only(rpc: Rpc, owner: str = "") -> None:
    if rpc.chain_id() == DEV_CHAIN_ID or bool(_owner_key(owner)):
        return
    raise HTTPException(403, "owner actions run only on the local test chain or when a test deployer key is configured")


def _usd8(v: int) -> float:
    return round(v / USD8, 2)


def _owner_tx(rpc: Rpc, contract: Contract, name: str, *args: Any, owner: str) -> str:
    key = _owner_key(owner)
    try:
        receipt = contract.transact(rpc, name, *args, sender=owner, key=key)
    except RpcError as err:
        raise HTTPException(409, revert_reason(err, contract) or str(err)) from err
    return receipt["transactionHash"]


@router.get("/api/catalog")
def catalog(ref: Reference = Depends(get_ref)) -> dict[str, Any]:
    markets: dict[str, dict[str, Any]] = {}
    for v in ref.venues.values():
        m = markets.setdefault(v.market, {"id": v.market, "label": MARKET_LABEL.get(v.market, v.market),
                                          "chain": MARKET_CHAIN.get(v.market, ""), "venues": []})
        m["venues"].append({"id": v.id, "name": v.name, "protocol": v.protocol, "action": v.action.value,
                            "accepts": list(v.accepts), "tier": int(v.tier)})
    for m in markets.values():
        m["assets"] = sorted({a for v in m["venues"] for a in v["accepts"]})
        m["actions"] = sorted({v["action"] for v in m["venues"]})
    return {"markets": markets}


@router.get("/api/vault/{account}")
def vault(account: Account) -> dict[str, Any]:
    market, rpc = _vault(account)
    dep = market.deployment
    acct = dep.account
    hook = Contract.load("TetherGuardHook", dep.hook)
    usdc = Contract.load("MockERC20", dep.usdc)

    eth_price = dep.eth_usd
    try:
        price, decimals = hook.call(rpc, "getLatestPrice", acct, NATIVE_ETH)
        eth_price = price / 10**decimals
    except Exception:  # feed not readable: fall back to the deployment price
        pass

    eth_bal = int(rpc.call("eth_getBalance", [acct, "latest"]), 16) / 10**18
    usdc_bal = usdc.call(rpc, "balanceOf", acct)[0] / USDC6
    holdings = []
    if eth_bal > 0:
        holdings.append({"symbol": "ETH", "where": "vault (idle)", "market": "crypto", "amount": round(eth_bal, 6), "usd": round(eth_bal * eth_price, 2)})
    if usdc_bal > 0:
        holdings.append({"symbol": "USDC", "where": "vault (idle)", "market": "crypto", "amount": round(usdc_bal, 2), "usd": round(usdc_bal, 2)})
    venue_of: dict[str, str] = {}
    for vid, addr in dep.venues.items():
        venue_of[addr.lower()] = vid
        pos = usdc.call(rpc, "balanceOf", addr)[0] / USDC6
        if pos > 0:
            holdings.append({"symbol": "USDC", "where": vid, "market": "crypto", "amount": round(pos, 2), "usd": round(pos, 2)})

    policy = hook.call(rpc, "getAccountPolicy", acct)[0]
    radius, baseline, ceiling, spent, epoch, tier, elastic, last_step, streak, owner = policy
    remaining = hook.call(rpc, "getRemainingRadius", acct)[0]
    session = _session_status(rpc, market)

    owner_eth_bal = 0.0
    owner_usdc_bal = 0.0
    try:
        owner_eth_bal = int(rpc.call("eth_getBalance", [owner, "latest"]), 16) / 10**18
        owner_usdc_bal = usdc.call(rpc, "balanceOf", owner)[0] / USDC6
    except Exception:
        pass

    ledger_records = _ledger(market.network)._read()

    reviews = []
    for rec in hook.call(rpc, "getPendingReviews", acct)[0]:
        rid, target, value, ts, status, note = rec
        tx_hash = ledger_records.get(str(rid), {}).get("tx_hash", "")
        reviews.append({
            "id": rid,
            "target": target,
            "venue_id": venue_of.get(target.lower()),
            "value_usd": _usd8(value),
            "timestamp": ts,
            "status": REVIEW_STATUS.get(status, str(status)),
            "note": note,
            "tx_hash": tx_hash,
        })

    recent_txs = []
    for rid_str, rec in sorted(ledger_records.items(), key=lambda x: int(x[0]), reverse=True):
        recent_txs.append({
            "id": int(rid_str),
            "venue_id": rec.get("venue_id", "venue"),
            "amount_usd": rec.get("amount_usd", 0.0),
            "tx_hash": rec.get("tx_hash", ""),
            "audit_record_hash": rec.get("audit_record_hash", ""),
            "market": market.network,
        })

    from tecc_brain.virtual_session.qr import render_qr_svg

    return {
        "live": True,
        "deposit_qr_svg": render_qr_svg(f"ethereum:{acct}@{dep.chain_id}", box_size=5, border=2),  # EIP-681 URI
        "network": market.network,
        "chain_id": dep.chain_id,
        "dev_chain": dep.chain_id == DEV_CHAIN_ID or bool(_owner_key(owner)),
        "deposit_address": acct,
        "root_owner": owner,
        "owner_wallet": {
            "address": owner,
            "eth": round(owner_eth_bal, 6),
            "usdc": round(owner_usdc_bal, 2),
            "usd_value": round(owner_eth_bal * eth_price + owner_usdc_bal, 2),
        },
        "contracts": {"account": acct, "hook": dep.hook, "validator": dep.validator, "usdc": dep.usdc},
        "eth_usd": round(eth_price, 2),
        "holdings": holdings,
        "total_usd": round(sum(h["usd"] for h in holdings), 2),
        "policy": {
            "radius_usd": _usd8(radius), "baseline_usd": _usd8(baseline), "ceiling_usd": _usd8(ceiling),
            "spent_today_usd": _usd8(spent), "remaining_usd": _usd8(remaining), "risk_tier": tier,
            "elasticity": elastic, "ratification_streak": streak,
        },
        "session_key": {"address": market.mandate.session_key, "authorized": session["authorized"], "layers": session,
                        "max_amount_usd": market.mandate.max_amount_usd, "valid_until": market.mandate.valid_until},
        "ai_heartbeat_alive": hook.call(rpc, "isAIHeartbeatAlive", acct)[0],
        "biometric_active": hook.call(rpc, "isBiometricActive", acct)[0],
        "executions": hook.call(rpc, "executionCount", acct)[0],
        "pending_reviews": reviews,
        "recent_transactions": recent_txs,
    }


class FaucetRequest(BaseModel):
    eth: float = Field(1.0, ge=0, le=100)
    usdc: float = Field(5000.0, ge=0, le=1_000_000)


@router.post("/api/vault/{account}/faucet")
def faucet(account: Account, req: FaucetRequest) -> dict[str, Any]:
    market, rpc = _vault(account)
    dep = market.deployment
    _dev_only(rpc, dep.root_owner)
    funder = dep.root_owner
    funder_key = _owner_key(funder)
    txs = []
    if req.eth > 0:
        if rpc.chain_id() == DEV_CHAIN_ID:
            anv_funder = rpc.call("eth_accounts")[0]
            txs.append(rpc.send_unlocked({"from": anv_funder, "to": dep.account, "value": hex(int(req.eth * 10**18))})["transactionHash"])
        elif funder_key:
            try:
                tx_h = rpc.send({"from": funder, "to": dep.account, "value": hex(int(req.eth * 10**18))}, funder_key)
                txs.append(tx_h)
            except Exception:
                pass
    if req.usdc > 0:
        txs.append(_owner_tx(rpc, Contract.load("MockERC20", dep.usdc), "mint", dep.account, int(req.usdc * USDC6), owner=funder))
    return {"ok": True, "tx_hashes": txs, "message": f"Test funds minted on-chain: {req.usdc:,.0f} USDC to smart vault."}


class ReviewRequest(BaseModel):
    record_id: int = Field(ge=0)
    action: Literal["ratify", "flag", "note"]
    note: str = Field("", max_length=280)
    penalize: bool = False


@router.post("/api/vault/{account}/review")
def review(account: Account, req: ReviewRequest) -> dict[str, Any]:
    market, rpc = _vault(account)
    dep = market.deployment
    _dev_only(rpc, dep.root_owner)
    hook = Contract.load("TetherGuardHook", dep.hook)
    owner = dep.root_owner
    if req.action == "ratify":
        tx = _owner_tx(rpc, hook, "ratifyTransaction", dep.account, req.record_id, owner=owner)
    elif req.action == "flag":
        tx = _owner_tx(rpc, hook, "flagTransactionForRevert", dep.account, req.record_id, req.note or "flagged in Morning Review", owner=owner)
    else:
        tx = _owner_tx(rpc, hook, "submitTransactionNote", dep.account, req.record_id, req.note, req.penalize, owner=owner)
    radius = hook.call(rpc, "getAccountPolicy", dep.account)[0][0]
    return {"ok": True, "tx_hash": tx, "radius_usd": _usd8(radius)}


class RadiusRequest(BaseModel):
    radius_usd: float = Field(gt=0, le=1_000_000)
    risk_tier: int = Field(2, ge=1, le=6)


@router.post("/api/vault/{account}/radius")
def set_radius(account: Account, req: RadiusRequest) -> dict[str, Any]:
    market, rpc = _vault(account)
    dep = market.deployment
    _dev_only(rpc, dep.root_owner)
    hook = Contract.load("TetherGuardHook", dep.hook)
    tx = _owner_tx(rpc, hook, "setTetherRadius", dep.account, int(req.radius_usd * USD8), req.risk_tier, owner=dep.root_owner)
    return {"ok": True, "tx_hash": tx, "radius_usd": _usd8(hook.call(rpc, "getAccountPolicy", dep.account)[0][0])}


class SessionRequest(BaseModel):
    authorized: bool


VAULT_OWNER_ACCOUNT = "demo"  # the one local deployment serves the demo account (see _vault)


def live_vault_state(account: str) -> VaultState | None:
    """Today's real leash from the deployed vault (radius, spend incl. cross-chain, AI heartbeat), so the Brain sizes
    its automatic slice to what the vault will actually accept. None when no vault is deployed or the node is down;
    callers then use what the request sent (default $500 radius, nothing spent)."""
    if account != VAULT_OWNER_ACCOUNT:
        return None
    market = _active_market()
    if market is None:
        return None
    try:
        rpc = Rpc(market.rpc_url)
        hook = Contract.load("TetherGuardHook", market.deployment.hook)
        acct = market.deployment.account
        radius = hook.call(rpc, "getAccountPolicy", acct)[0][0]
        remaining = hook.call(rpc, "getRemainingRadius", acct)[0]
        alive = bool(hook.call(rpc, "isAIHeartbeatAlive", acct)[0])
    except (RpcError, OSError, ValueError):
        return None
    radius_usd = _usd8(radius)
    return VaultState(tether_radius_usd=radius_usd, spent_today_usd=max(0.0, radius_usd - _usd8(remaining)),
                      heartbeat_alive=alive)


def resolve_vault(account: str, vault_in: Any, sent: bool) -> VaultState:
    """The vault state a decision uses: what the caller sent explicitly, else the live vault, else the defaults."""
    if not sent:
        live = live_vault_state(account)
        if live is not None:
            return live
    return vault_in.to_state()


def open_live_biometric_window(account: str) -> bool:
    """After the user's passkey was verified (P-256, /api/biometrics/verify), open the vault's own biometric window
    so a tether-breaking order can pass the hook. Local test chain only: on a real network the user's device
    submits `completeBiometricVerificationWithWebAuthn` itself. Returns whether the on-chain window is open."""
    market = load_market(_network())
    if market is None:
        return False
    try:
        rpc = Rpc(market.rpc_url)
        if rpc.chain_id() != DEV_CHAIN_ID:
            return False
        hook = Contract.load("TetherGuardHook", market.deployment.hook)
        if not hook.call(rpc, "isBiometricActive", market.deployment.account)[0]:
            hook.transact(rpc, "completeBiometricVerification", market.deployment.account, sender=market.deployment.root_owner)
        return True
    except (RpcError, OSError, HTTPException):
        return False


def _session_status(rpc: Rpc, market: MarketFile) -> dict[str, bool]:
    """The session key can act only while ALL three layers allow it. `executor_installed` is the one the account's
    `execute` actually checks; the validator gates its signatures; the hook flag gates radius calibration."""
    dep, key = market.deployment, market.mandate.session_key
    executor = bool(Contract.load("TecAccount", dep.account).call(rpc, "installedExecutors", key)[0])
    validator = bool(Contract.load("SessionKeyValidator", dep.validator).call(rpc, "sessionKeys", dep.account, key)[4])
    hook = bool(Contract.load("TetherGuardHook", dep.hook).call(rpc, "authorizedSessionKeys", dep.account, key)[0])
    return {"authorized": executor and validator and hook, "executor_installed": executor,
            "validator_active": validator, "hook_authorized": hook}


@router.post("/api/vault/{account}/session")
def set_session(account: Account, req: SessionRequest) -> dict[str, Any]:
    """The killswitch: the vault stops accepting anything from the Brain's session key.

    Revoking removes every layer the key relies on: the account uninstalls it as an ERC-7579 executor (what
    `TecAccount.execute` checks), the SessionKeyValidator deactivates it, and the hook drops its authorization.
    Restoring re-provisions all three. Owner-only, local test chain only."""
    market, rpc = _vault(account)
    dep, key, owner = market.deployment, market.mandate.session_key, market.deployment.root_owner
    _dev_only(rpc, owner)
    if req.authorized:
        try:
            provision_session_key(rpc, dep, market.mandate, fund_wei=0)
        except RpcError as err:
            raise HTTPException(409, f"could not restore the session key: {err}") from err
    else:
        hook = Contract.load("TetherGuardHook", dep.hook)
        acct = Contract.load("TecAccount", dep.account)
        validator = Contract.load("SessionKeyValidator", dep.validator)
        # the owner calls the validator through the account, which the hook allows inside a biometric window
        _owner_tx(rpc, hook, "completeBiometricVerification", dep.account, owner=owner)
        try:
            revoke = validator.encode("revokeSessionKey", dep.account, key)
            _owner_tx(rpc, acct, "execute", b"\x00" * 32, execution_calldata(dep.validator, 0, revoke), owner=owner)
            _owner_tx(rpc, hook, "setSessionKeyAuthorization", dep.account, key, False, owner=owner)
            _owner_tx(rpc, acct, "uninstallModule", MODULE_TYPE_EXECUTOR, key, b"", owner=owner)
        finally:
            _owner_tx(rpc, hook, "revokeBiometricVerification", dep.account, owner=owner)
    status = _session_status(rpc, market)
    return {"ok": True, **status}


class WithdrawRequest(BaseModel):
    to: str = Field(pattern=r"^0x[0-9a-fA-F]{40}$")
    asset: Literal["ETH", "USDC"]
    amount: float = Field(gt=0)


@router.post("/api/vault/{account}/withdraw")
def withdraw(account: Account, req: WithdrawRequest) -> dict[str, Any]:
    """Only the owner can send money out, and only inside a verified biometric (passkey) window."""
    from tecc_brain.api.biometrics import get_biometric_manager

    market, rpc = _vault(account)
    _dev_only(rpc)
    active, _ = get_biometric_manager().is_biometric_window_active(account)
    if not active:
        raise HTTPException(403, "verify with your passkey (FaceID / Touch ID) first: withdrawals need the biometric window")
    dep = market.deployment
    hook = Contract.load("TetherGuardHook", dep.hook)
    # The passkey signature was verified (P-256) by the biometrics service; the vault keeps its own window, which
    # the owner opens here. On a real network the device submits completeBiometricVerificationWithWebAuthn itself.
    if not hook.call(rpc, "isBiometricActive", dep.account)[0]:
        _owner_tx(rpc, hook, "completeBiometricVerification", dep.account, owner=dep.root_owner)
    acct = Contract.load("TecAccount", dep.account)
    if req.asset == "ETH":
        calldata = execution_calldata(req.to, int(req.amount * 10**18), b"")
    else:
        usdc = Contract.load("MockERC20", dep.usdc)
        calldata = execution_calldata(dep.usdc, 0, usdc.encode("transfer", req.to, int(req.amount * USDC6)))
    tx = _owner_tx(rpc, acct, "execute", b"\x00" * 32, calldata, owner=dep.root_owner)
    return {"ok": True, "tx_hash": tx, "message": f"Sent {req.amount:g} {req.asset} to {req.to}."}

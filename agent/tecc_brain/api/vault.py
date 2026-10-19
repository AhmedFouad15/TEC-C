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

import os
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tecc_brain.api.deps import Account, get_ref
from tecc_brain.onchain.artifacts import NATIVE_ETH, Contract, revert_reason
from tecc_brain.onchain.markets import MarketFile, load_market
from tecc_brain.onchain.rpc import Rpc, RpcError
from tecc_brain.onchain.session import execution_calldata
from tecc_brain.reference import Reference

router = APIRouter(tags=["vault"])

DEV_CHAIN_ID = 31337
USD8 = 10**8  # the hook meters everything in 8-decimal USD
USDC6 = 10**6
MARKET_LABEL = {"crypto": "Crypto", "chinese_market": "Chinese market", "commodities": "Commodities", "arbitrage": "Arbitrage"}
MARKET_CHAIN = {"crypto": "Ethereum", "chinese_market": "FISCO BCOS", "commodities": "Arbitrum", "arbitrage": "PegGuard"}
REVIEW_STATUS = {0: "pending", 1: "ratified", 2: "flagged", 3: "noted"}


def _network() -> str:
    return os.environ.get("TECC_NETWORK", "anvil")


def _vault(account: str) -> tuple[MarketFile, Rpc]:
    """The deployed vault behind this account. One local deployment serves the demo account."""
    market = load_market(_network())
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


def _dev_only(rpc: Rpc) -> None:
    if rpc.chain_id() != DEV_CHAIN_ID:
        raise HTTPException(403, "owner actions run only on the local test chain; on real networks the user's device signs them")


def _usd8(v: int) -> float:
    return round(v / USD8, 2)


def _owner_tx(rpc: Rpc, contract: Contract, name: str, *args: Any, owner: str) -> str:
    try:
        receipt = contract.transact(rpc, name, *args, sender=owner)
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
    holdings = [
        {"symbol": "ETH", "where": "vault (idle)", "market": "crypto", "amount": round(eth_bal, 6), "usd": round(eth_bal * eth_price, 2)},
        {"symbol": "USDC", "where": "vault (idle)", "market": "crypto", "amount": round(usdc_bal, 2), "usd": round(usdc_bal, 2)},
    ]
    venue_of: dict[str, str] = {}
    for vid, addr in dep.venues.items():
        venue_of[addr.lower()] = vid
        pos = usdc.call(rpc, "balanceOf", addr)[0] / USDC6
        if pos > 0:
            holdings.append({"symbol": "USDC", "where": vid, "market": "crypto", "amount": round(pos, 2), "usd": round(pos, 2)})

    policy = hook.call(rpc, "getAccountPolicy", acct)[0]
    radius, baseline, ceiling, spent, epoch, tier, elastic, last_step, streak, owner = policy
    remaining = hook.call(rpc, "getRemainingRadius", acct)[0]
    authorized = hook.call(rpc, "authorizedSessionKeys", acct, market.mandate.session_key)[0]

    reviews = []
    for rec in hook.call(rpc, "getPendingReviews", acct)[0]:
        rid, target, value, ts, status, note = rec
        reviews.append({"id": rid, "target": target, "venue_id": venue_of.get(target.lower()),
                        "value_usd": _usd8(value), "timestamp": ts, "status": REVIEW_STATUS.get(status, str(status)), "note": note})

    from tecc_brain.virtual_session.qr import render_qr_svg

    return {
        "live": True,
        "deposit_qr_svg": render_qr_svg(f"ethereum:{acct}@{dep.chain_id}", box_size=5, border=2),  # EIP-681 URI
        "network": market.network,
        "chain_id": dep.chain_id,
        # no rpc_url here: on a real network it usually embeds the provider's API key (Infura/Alchemy path)
        "dev_chain": dep.chain_id == DEV_CHAIN_ID,
        "deposit_address": acct,
        "root_owner": owner,
        "contracts": {"account": acct, "hook": dep.hook, "validator": dep.validator, "usdc": dep.usdc},
        "eth_usd": round(eth_price, 2),
        "holdings": holdings,
        "total_usd": round(sum(h["usd"] for h in holdings), 2),
        "policy": {
            "radius_usd": _usd8(radius), "baseline_usd": _usd8(baseline), "ceiling_usd": _usd8(ceiling),
            "spent_today_usd": _usd8(spent), "remaining_usd": _usd8(remaining), "risk_tier": tier,
            "elasticity": elastic, "ratification_streak": streak,
        },
        "session_key": {"address": market.mandate.session_key, "authorized": authorized,
                        "max_amount_usd": market.mandate.max_amount_usd, "valid_until": market.mandate.valid_until},
        "ai_heartbeat_alive": hook.call(rpc, "isAIHeartbeatAlive", acct)[0],
        "biometric_active": hook.call(rpc, "isBiometricActive", acct)[0],
        "executions": hook.call(rpc, "executionCount", acct)[0],
        "pending_reviews": reviews,
    }


class FaucetRequest(BaseModel):
    eth: float = Field(1.0, ge=0, le=100)
    usdc: float = Field(5000.0, ge=0, le=1_000_000)


@router.post("/api/vault/{account}/faucet")
def faucet(account: Account, req: FaucetRequest) -> dict[str, Any]:
    market, rpc = _vault(account)
    _dev_only(rpc)
    dep = market.deployment
    funder = rpc.call("eth_accounts")[0]
    txs = []
    if req.eth > 0:
        txs.append(rpc.send_unlocked({"from": funder, "to": dep.account, "value": hex(int(req.eth * 10**18))})["transactionHash"])
    if req.usdc > 0:
        txs.append(_owner_tx(rpc, Contract.load("MockERC20", dep.usdc), "mint", dep.account, int(req.usdc * USDC6), owner=funder))
    return {"ok": True, "tx_hashes": txs, "message": f"Test funds sent: {req.eth:g} ETH and {req.usdc:,.0f} USDC."}


class ReviewRequest(BaseModel):
    record_id: int = Field(ge=0)
    action: Literal["ratify", "flag", "note"]
    note: str = Field("", max_length=280)
    penalize: bool = False


@router.post("/api/vault/{account}/review")
def review(account: Account, req: ReviewRequest) -> dict[str, Any]:
    market, rpc = _vault(account)
    _dev_only(rpc)
    dep = market.deployment
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
    _dev_only(rpc)
    dep = market.deployment
    hook = Contract.load("TetherGuardHook", dep.hook)
    tx = _owner_tx(rpc, hook, "setTetherRadius", dep.account, int(req.radius_usd * USD8), req.risk_tier, owner=dep.root_owner)
    return {"ok": True, "tx_hash": tx, "radius_usd": _usd8(hook.call(rpc, "getAccountPolicy", dep.account)[0][0])}


class SessionRequest(BaseModel):
    authorized: bool


@router.post("/api/vault/{account}/session")
def set_session(account: Account, req: SessionRequest) -> dict[str, Any]:
    """The killswitch: the vault stops accepting anything signed by the Brain's session key."""
    market, rpc = _vault(account)
    _dev_only(rpc)
    dep = market.deployment
    hook = Contract.load("TetherGuardHook", dep.hook)
    tx = _owner_tx(rpc, hook, "setSessionKeyAuthorization", dep.account, market.mandate.session_key, req.authorized, owner=dep.root_owner)
    return {"ok": True, "tx_hash": tx, "authorized": hook.call(rpc, "authorizedSessionKeys", dep.account, market.mandate.session_key)[0]}


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

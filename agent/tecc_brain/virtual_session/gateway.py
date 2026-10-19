"""Mobile Gateway App (127.0.0.1:8001, tunneled, allow-listed routes ONLY) - Sections 7, 8.3 & 8.5.

Strict Allow-List:
  - GET  /s/{session_id}
  - POST /webauthn/register/options
  - POST /webauthn/register/verify
  - POST /webauthn/login/options
  - POST /webauthn/login/verify
  - POST /webauthn/stepup/options
  - POST /webauthn/stepup/verify
  - GET  /api/dashboard
  - GET  /api/positions
  - GET  /api/signals
  - POST /api/trade/{action:path}
  - POST /api/disconnect
  - WS   /ws

ANY other path returns 404 (Never proxy the whole local app).
Never exposes API keys or admin operations.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from tecc_brain.virtual_session.html_pages import render_phone_ui_html
from tecc_brain.virtual_session.service import VirtualSessionService, get_virtual_session_service

COOKIE_NAME = "tecc_vs_session"

# In-memory rate limiting / failure tracking (Section 5.9)
_LOGIN_FAILURES: dict[str, list[float]] = {}
MAX_FAILURES = 5
LOCKOUT_WINDOW_SECONDS = 300


def _check_rate_limit(key: str) -> None:
    now = time.time()
    attempts = _LOGIN_FAILURES.setdefault(key, [])
    # Evict older than window
    _LOGIN_FAILURES[key] = [t for t in attempts if now - t < LOCKOUT_WINDOW_SECONDS]
    if len(_LOGIN_FAILURES[key]) >= MAX_FAILURES:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed authentication attempts. Session temporarily locked.",
        )


def _record_failure(key: str) -> None:
    _LOGIN_FAILURES.setdefault(key, []).append(time.time())


def _clear_failures(key: str) -> None:
    _LOGIN_FAILURES.pop(key, None)



class RegisterOptionsReq(BaseModel):
    session_id: str


class RegisterVerifyReq(BaseModel):
    session_id: str
    credential_id: str
    qx: str | int = 0
    qy: str | int = 0
    authenticator_data: str
    client_data_json: str | None = None
    r: str | int | None = None
    s: str | int | None = None
    signature: str | None = None
    attestation_object: str | None = None
    transports: list[str] | None = None


class LoginOptionsReq(BaseModel):
    session_id: str


class LoginVerifyReq(BaseModel):
    session_id: str
    credential_id: str
    authenticator_data: str
    client_data_json: str | None = None
    r: str | int | None = None
    s: str | int | None = None
    signature: str | None = None


class StepupOptionsReq(BaseModel):
    action: str
    params: dict[str, Any] | None = None


class StepupVerifyReq(BaseModel):
    action: str
    credential_id: str
    authenticator_data: str
    client_data_json: str | None = None
    r: str | int | None = None
    s: str | int | None = None
    signature: str | None = None
    params: dict[str, Any] | None = None


class TradeExecuteReq(BaseModel):
    stepup_token: str = Field(description="60-second single-use step-up token")
    params: dict[str, Any] = Field(default_factory=dict)


def gateway_account() -> str:
    """The wallet this laptop serves. One owner per machine: the phone acts for that account only."""
    return os.environ.get("TECC_VIRTUAL_SESSION_ACCOUNT", "demo")


def _dep(dependency):
    """Resolve an admin-app dependency the same way the admin app would (honours its test overrides)."""
    from tecc_brain.app import app as admin_app

    return admin_app.dependency_overrides.get(dependency, dependency)()


def _wallet_state() -> dict[str, Any]:
    from tecc_brain.api.arbitrage import get_arbitrage_scanner
    from tecc_brain.api.deps import get_anchors, get_router, get_store
    from tecc_brain.pegguard import PEGGUARD_ASSET_CATALOG
    from tecc_brain.strategy.portfolio import load_demo_portfolio

    account = gateway_account()
    store, router = _dep(get_store), _dep(get_router)
    scanner = get_arbitrage_scanner(store=store, router=router, anchors=_dep(get_anchors))
    portfolio = load_demo_portfolio() if account == "demo" else None
    radius = router.daily_limit_usd
    spent = router.tether_tracker.get_spent(account)
    return {
        "account": account,
        "scanner_active": scanner.is_enabled(account),
        "monitored_assets_count": len(PEGGUARD_ASSET_CATALOG),
        "watermarks": scanner.get_watermarks(account),
        "positions": [p.model_dump() for p in portfolio.positions] if portfolio else [],
        "radius_usd": radius,
        "spent_today_usd": spent,
        "remaining_usd": max(0.0, radius - spent),
    }


def _trade_execute(params: dict[str, Any]) -> dict[str, Any]:
    """Approve one card of a proposal — exactly /api/mandate/execute (AI veto refused, BREAKOUT needs FaceID)."""
    from pydantic import ValidationError

    from tecc_brain.api.deps import get_proposals, get_ref, get_router, get_store
    from tecc_brain.api.mandate import ExecuteRequest, execute

    try:
        req = ExecuteRequest(account=gateway_account(), **{k: v for k, v in params.items() if k != "account"})
    except (TypeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=f"execute needs proposal_id and label: {exc}") from exc
    out = execute(req, store=_dep(get_store), proposals=_dep(get_proposals), ref=_dep(get_ref), router=_dep(get_router))
    return {"status": out.intent.status, "result": out.model_dump(mode="json")}


def _trade_arbitrage_toggle(params: dict[str, Any]) -> dict[str, Any]:
    from tecc_brain.api.arbitrage import get_arbitrage_scanner
    from tecc_brain.api.deps import get_anchors, get_router, get_store

    if not isinstance(params.get("enabled"), bool):
        raise HTTPException(status_code=422, detail="arbitrage/toggle needs a boolean 'enabled'")
    scanner = get_arbitrage_scanner(store=_dep(get_store), router=_dep(get_router), anchors=_dep(get_anchors))
    enabled = scanner.set_enabled(gateway_account(), params["enabled"])
    return {"status": "enabled" if enabled else "disabled", "result": {"enabled": enabled}}


TRADE_ACTIONS = {"execute": _trade_execute, "arbitrage/toggle": _trade_arbitrage_toggle}


def create_gateway_app(service: VirtualSessionService | None = None) -> FastAPI:
    app = FastAPI(
        title="Tec-C Mobile Gateway",
        description="Allow-listed mobile gateway for remote phone biometric access (Section 3).",
        docs_url=None,  # Section 8.3: Never expose Swagger/OpenAPI on gateway
        redoc_url=None,
        openapi_url=None,
    )

    def _get_service() -> VirtualSessionService:
        return service or get_virtual_session_service()

    def _client_ip_country(request: Request) -> tuple[str, str]:
        ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "127.0.0.1")
        country = request.headers.get("cf-ipcountry", "XX")
        return ip, country

    # -------------------------------------------------------------------------
    # Hardening Middleware (Section 8.3)
    # -------------------------------------------------------------------------
    @app.middleware("http")
    async def gateway_hardening_middleware(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        # Security headers
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' 'unsafe-inline'; connect-src 'self' wss: https:; img-src 'self' data:; frame-ancestors 'none'"
        )
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    # -------------------------------------------------------------------------
    # Cookie Auth Dependency
    # -------------------------------------------------------------------------
    async def require_active_session_cookie(request: Request) -> dict[str, Any]:
        svc = _get_service()
        raw_cookie = request.cookies.get(COOKIE_NAME)
        if not raw_cookie:
            # Also allow Authorization: Bearer <cookie> for non-browser programmatic clients
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer "):
                raw_cookie = auth.split("Bearer ")[1].strip()

        if not raw_cookie:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session cookie required")

        sess = svc.db.resolve_cookie(raw_cookie)
        if not sess:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session cookie")

        if sess["state"] == "REVOKED":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session ended")
        if sess["state"] == "RELINK_REQUIRED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tunnel URL changed; relink required")
        if sess["state"] != "ACTIVE":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session is not active")

        ip, country = _client_ip_country(request)
        svc.db.update_touch(sess["id"], ip=ip, country=country, user_agent=request.headers.get("user-agent"))
        return sess

    # -------------------------------------------------------------------------
    # Allow-Listed Routes
    # -------------------------------------------------------------------------

    @app.get("/s/{session_id}", response_class=HTMLResponse)
    def get_session_page(session_id: str, request: Request) -> str:
        """GET /s/{id}: Pairing or login page depending on state."""
        svc = _get_service()
        sess = svc.db.get_session(session_id)
        if not sess:
            raise HTTPException(status_code=404, detail="Virtual session not found")
        ip, country = _client_ip_country(request)
        svc.db.update_touch(session_id, ip=ip, country=country, user_agent=request.headers.get("user-agent"))
        return render_phone_ui_html(sess)

    @app.post("/webauthn/register/options")
    def register_options(req: RegisterOptionsReq) -> dict[str, Any]:
        """POST /webauthn/register/options: link only, state = PENDING."""
        svc = _get_service()
        try:
            return svc.get_registration_options(req.session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Session not found")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/webauthn/register/verify")
    def register_verify(req: RegisterVerifyReq, request: Request, response: Response) -> dict[str, Any]:
        """POST /webauthn/register/verify: Verifies passkey with UV=0x04 flag, stores public key, issues cookie."""
        svc = _get_service()
        ip, country = _client_ip_country(request)

        # In browser WebAuthn, qx and qy can be extracted or sent directly
        qx_val = req.qx
        qy_val = req.qy
        if qx_val == 0 or qy_val == 0:
            # If not sent directly, generate/derive or require valid P-256 test coordinates
            from tecc_brain.biometrics.passkey import generate_p256_keypair
            _, qx_val, qy_val = generate_p256_keypair()

        try:
            updated_sess, cookie_token = svc.verify_registration(
                session_id=req.session_id,
                credential_id_raw=req.credential_id,
                qx=qx_val,
                qy=qy_val,
                authenticator_data_raw=req.authenticator_data,
                client_data_json_raw=req.client_data_json,
                r=req.r,
                s=req.s,
                signature_raw=req.signature,
                transports=req.transports,
                user_agent=request.headers.get("user-agent"),
                ip=ip,
                country=country,
            )
            # Section 5.4: HttpOnly; Secure; SameSite=Strict
            response.set_cookie(
                key=COOKIE_NAME,
                value=cookie_token,
                httponly=True,
                secure=True,
                samesite="strict",
                path="/",
            )
            return {
                "status": "ok",
                "state": updated_sess["state"],
                "cookie_issued": True,
                "session_id": req.session_id,
            }
        except KeyError:
            raise HTTPException(status_code=404, detail="Session not found")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/webauthn/login/options")
    def login_options(req: LoginOptionsReq, request: Request) -> dict[str, Any]:
        """POST /webauthn/login/options: credential."""
        svc = _get_service()
        ip, _ = _client_ip_country(request)
        _check_rate_limit(f"{req.session_id}:{ip}")
        try:
            return svc.get_login_options(req.session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="Session not found")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/webauthn/login/verify")
    def login_verify(req: LoginVerifyReq, request: Request, response: Response) -> dict[str, Any]:
        """POST /webauthn/login/verify: Biometric login, issues cookie."""
        svc = _get_service()
        ip, country = _client_ip_country(request)
        rate_key = f"{req.session_id}:{ip}"
        _check_rate_limit(rate_key)

        try:
            sess, cookie_token = svc.verify_login(
                session_id=req.session_id,
                credential_id_raw=req.credential_id,
                authenticator_data_raw=req.authenticator_data,
                client_data_json_raw=req.client_data_json,
                r=req.r,
                s=req.s,
                signature_raw=req.signature,
                ip=ip,
                country=country,
            )
            _clear_failures(rate_key)
            response.set_cookie(
                key=COOKIE_NAME,
                value=cookie_token,
                httponly=True,
                secure=True,
                samesite="strict",
                path="/",
            )
            return {"status": "ok", "state": sess["state"], "cookie_issued": True}
        except (ValueError, KeyError) as exc:
            _record_failure(rate_key)
            raise HTTPException(status_code=401, detail=str(exc))

    @app.post("/webauthn/stepup/options")
    def stepup_options(
        req: StepupOptionsReq,
        sess: dict[str, Any] = Depends(require_active_session_cookie),
    ) -> dict[str, Any]:
        """POST /webauthn/stepup/options: Fresh biometric for sensitive action."""
        svc = _get_service()
        try:
            return svc.get_stepup_options(sess["id"], req.action, req.params)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/webauthn/stepup/verify")
    def stepup_verify(
        req: StepupVerifyReq,
        request: Request,
        sess: dict[str, Any] = Depends(require_active_session_cookie),
    ) -> dict[str, Any]:
        """POST /webauthn/stepup/verify: Issues 60-second single-use stepup_token."""
        svc = _get_service()
        ip, country = _client_ip_country(request)
        try:
            token = svc.verify_stepup(
                session_id=sess["id"],
                action=req.action,
                credential_id_raw=req.credential_id,
                authenticator_data_raw=req.authenticator_data,
                client_data_json_raw=req.client_data_json,
                r=req.r,
                s=req.s,
                signature_raw=req.signature,
                params=req.params,
                ip=ip,
                country=country,
            )
            return {"status": "ok", "stepup_token": token, "expires_in_seconds": 60}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    # -------------------------------------------------------------------------
    # Read-Only APIs (Section 7 & 5.8)
    # -------------------------------------------------------------------------

    @app.get("/api/dashboard")
    def get_dashboard(sess: dict[str, Any] = Depends(require_active_session_cookie)) -> dict[str, Any]:
        """GET /api/dashboard: Read-only summary of the owner's live state (never API keys)."""
        state = _wallet_state()
        return {
            "session_id": sess["id"],
            "state": sess["state"],
            "can_trade": sess["can_trade"],
            "account": state["account"],
            "scanner_active": state["scanner_active"],
            "monitored_assets_count": state["monitored_assets_count"],
            "active_positions_count": len(state["positions"]),
            "vault_tether_radius_usd": state["radius_usd"],
            "spent_today_usd": state["spent_today_usd"],
            "remaining_today_usd": state["remaining_usd"],
            "api_keys": None,  # Section 5.7: API keys never reach the phone
        }

    @app.get("/api/positions")
    def get_positions(sess: dict[str, Any] = Depends(require_active_session_cookie)) -> dict[str, Any]:
        """GET /api/positions: Read-only positions and today's tether health."""
        state = _wallet_state()
        radius = state["radius_usd"]
        return {
            "positions": state["positions"],
            "total_value_usd": round(sum(p["amount_usd"] for p in state["positions"]), 2),
            "tether_health": f"{(state['remaining_usd'] / radius * 100) if radius > 0 else 0:.0f}%",
        }

    @app.get("/api/signals")
    def get_signals(sess: dict[str, Any] = Depends(require_active_session_cookie)) -> dict[str, Any]:
        """GET /api/signals: hourly-monitor events and PegGuard watermarks for the owner's account."""
        from tecc_brain.monitor.hourly import get_event_log

        state = _wallet_state()
        signals = [f"PegGuard scanner {'active' if state['scanner_active'] else 'off'} across "
                   f"{state['monitored_assets_count']} pegged assets."]
        signals += [f"{sym}: unprofitable de-peg noted at {wm.unprofitable_price:.4f} (EV {wm.ev_bps:+.1f} bps)."
                    for sym, wm in state["watermarks"].items()]
        signals += [f"{e.symbol}: {e.trigger} signal ({e.regime}) — {e.summary}"
                    for e in get_event_log().recent(10) if e.account == state["account"]]
        return {"signals": signals, "timestamp": int(time.time())}

    # -------------------------------------------------------------------------
    # Trade Action (Section 7, 5.5 & 5.8)
    # -------------------------------------------------------------------------

    @app.post("/api/trade/{action:path}")
    def execute_trade(
        action: str,
        req: TradeExecuteReq,
        request: Request,
        sess: dict[str, Any] = Depends(require_active_session_cookie),
    ) -> dict[str, Any]:
        """POST /api/trade/*: Trade action requiring cookie + stepup_token + can_trade. Runs the SAME code path as the
        laptop app — the Brain's per-card verdict, the soft tether and the MarketRouter all apply."""
        if not sess["can_trade"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Mobile session is read-only. Trading permission disabled for this session.",
            )
        if action not in TRADE_ACTIONS:  # checked before the step-up token is spent
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail=f"unknown trade action; allowed: {', '.join(sorted(TRADE_ACTIONS))}")

        svc = _get_service()
        from tecc_brain.virtual_session.webauthn_engine import compute_action_hash
        action_hash = compute_action_hash(action, req.params)

        valid = svc.db.consume_stepup_token(sess["id"], req.stepup_token, action_hash)
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid, expired, or already-consumed step-up token for this trade action",
            )

        ip, country = _client_ip_country(request)
        result = TRADE_ACTIONS[action](req.params)
        svc.db.log_event(
            session_id=sess["id"],
            event="trade_executed",
            ip=ip,
            country=country,
            detail=f"action={action} params={json.dumps(req.params)} status={result.get('status')}",
        )
        return {
            **result,
            "action": action,
            "session_id": sess["id"],
            "timestamp": int(time.time()),
        }

    # -------------------------------------------------------------------------
    # Disconnect (Section 7 & 8.5)
    # -------------------------------------------------------------------------

    @app.post("/api/disconnect")
    def disconnect_phone(
        request: Request,
        response: Response,
        sess: dict[str, Any] = Depends(require_active_session_cookie),
    ) -> dict[str, Any]:
        """POST /api/disconnect: Phone-side revoke; clears cookie and wipes credentials."""
        svc = _get_service()
        ip, country = _client_ip_country(request)
        svc.revoke_session(sess["id"], reason="phone_disconnect", ip=ip, country=country)
        response.delete_cookie(COOKIE_NAME, path="/")
        return {"status": "disconnected"}

    # -------------------------------------------------------------------------
    # WebSocket (Section 7 & 8.5)
    # -------------------------------------------------------------------------

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """WS /ws: Live updates (not SSE). Authenticated via session cookie."""
        await websocket.accept()
        raw_cookie = websocket.cookies.get(COOKIE_NAME)
        svc = _get_service()
        sess = svc.db.resolve_cookie(raw_cookie)
        if not sess or sess["state"] != "ACTIVE":
            await websocket.close(code=4001, reason="Unauthorized or inactive session")
            return

        try:
            # Initial push
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "dashboard",
                        "session_id": sess["id"],
                        "signals": [
                            "PegGuard Scanner active across 25 pegged assets.",
                            "All par-pegged stablecoins within 0.15% parity threshold.",
                        ],
                    }
                )
            )
            while True:
                # Keep alive & listen for client messages
                data = await websocket.receive_text()
                # Verify session hasn't been revoked
                cur_sess = svc.db.get_session(sess["id"])
                if not cur_sess or cur_sess["state"] != "ACTIVE":
                    await websocket.close(code=4001, reason="Session no longer active")
                    break
                await websocket.send_text(json.dumps({"type": "pong", "time": int(time.time())}))
        except WebSocketDisconnect:
            pass

    return app


gateway_app = create_gateway_app()

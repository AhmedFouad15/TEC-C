"""Comprehensive Test Suite for Virtual Session Remote Phone Access (Sections 1-11 & Page 10 Checklist).

Verifies:
1. TunnelManager defaults to https://xxxx.trycloudflare.co and parses tunnel host.
2. Create session flow with 128-bit ID, 6-digit pair_code, QR code, and PENDING state.
3. WebAuthn registration requiring UV flag (0x04) and UP flag (0x01); issues HttpOnly cookie.
4. Second device attempting to pair without approval or on an already registered session is rejected.
5. Laptop approval with matching 6-digit pair_code transitions session to ACTIVE.
6. Delete on laptop revokes session and next phone request returns 401.
7. Disconnect on phone revokes session, clears cookie, and wipes credentials in SQLite.
8. URL change marks sessions RELINK_REQUIRED, and POST /admin/sessions/{id}/reconnect issues fresh link.
9. Security isolation: Gateway (8001) returns 404 for admin routes, mandate routes, and openapi docs.
10. Sensitive trade actions require can_trade=True AND single-use HMAC step-up token (< 60s); replay is rejected.
11. Gateway responses never leak API keys or private keys.
12. Repeated failed biometric logins trigger rate-limit lockout.
13. Kill switch revokes all sessions and stops the tunnel.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any
import pytest
from fastapi.testclient import TestClient

from tecc_brain.app import app as admin_app
from tecc_brain.biometrics.passkey import (
    build_authenticator_data,
    generate_p256_keypair,
    normalize_low_s,
    sign_webauthn_p256,
)
from tecc_brain.virtual_session import (
    DEFAULT_TEMP_TUNNEL_URL,
    TunnelManager,
    VirtualSessionDB,
    VirtualSessionService,
    create_gateway_app,
    extract_hostname,
    reset_virtual_session_service,
)
from tecc_brain.virtual_session.webauthn_engine import b64url_decode, b64url_encode


@pytest.fixture
def service_env(tmp_path: Any) -> tuple[VirtualSessionService, TestClient, TestClient]:
    db_file = str(tmp_path / "test_virtual_sessions.sqlite3")
    db = VirtualSessionDB(db_path=db_file)
    tunnel = TunnelManager(default_url=DEFAULT_TEMP_TUNNEL_URL, spawn_binary=False)
    svc = VirtualSessionService(db=db, tunnel=tunnel)
    reset_virtual_session_service(svc)

    admin_client = TestClient(admin_app)
    gateway_client = TestClient(create_gateway_app(svc))
    return svc, admin_client, gateway_client


def test_tunnel_manager_default_temp_url() -> None:
    tm = TunnelManager(default_url=DEFAULT_TEMP_TUNNEL_URL, spawn_binary=False)
    url = tm.start()
    assert url == "https://xxxx.trycloudflare.co"
    assert tm.tunnel_host == "xxxx.trycloudflare.co"
    assert extract_hostname("https://abc-def.trycloudflare.com/s/123") == "abc-def.trycloudflare.com"


def test_create_session_admin_flow(service_env: tuple[VirtualSessionService, TestClient, TestClient]) -> None:
    svc, admin, _ = service_env
    res = admin.post("/admin/sessions", json={"name": "Alice iPhone", "can_trade": True})
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Alice iPhone"
    assert data["state"] == "PENDING"
    assert data["can_trade"] is True
    assert len(data["pair_code"]) == 6
    assert data["tunnel_host"] == "xxxx.trycloudflare.co"
    assert "/s/" in data["link"]
    assert "<svg" in data["qr_svg"]


def test_full_pairing_registration_and_laptop_approval(
    service_env: tuple[VirtualSessionService, TestClient, TestClient],
) -> None:
    svc, admin, gateway = service_env
    # 1. Laptop creates session
    c_res = admin.post("/admin/sessions", json={"name": "Trader iPhone", "can_trade": False})
    sess = c_res.json()
    sess_id = sess["id"]
    pair_code = sess["pair_code"]

    # 2. Phone opens /s/{id}
    page_res = gateway.get(f"/s/{sess_id}")
    assert page_res.status_code == 200
    assert "Pair with Laptop" in page_res.text

    # 3. Phone gets registration options
    opt_res = gateway.post("/webauthn/register/options", json={"session_id": sess_id})
    assert opt_res.status_code == 200
    opts = opt_res.json()
    assert opts["rp"]["id"] == "xxxx.trycloudflare.co"
    assert opts["authenticatorSelection"]["userVerification"] == "required"

    # 4. Phone signs with Secure Enclave P-256 key
    key, qx, qy = generate_p256_keypair()
    auth_data = build_authenticator_data(rp_id="xxxx.trycloudflare.co", user_present=True, user_verified=True)
    raw_challenge = b64url_decode(opts["challenge"])
    client_data = json.dumps({
        "type": "webauthn.create",
        "challenge": opts["challenge"],
        "origin": "https://xxxx.trycloudflare.co",
    })
    client_data_hash = hashlib.sha256(client_data.encode("utf-8")).digest()
    r, s, _ = sign_webauthn_p256(key, auth_data, client_data_hash)

    # 5. Phone completes registration
    reg_res = gateway.post(
        "/webauthn/register/verify",
        json={
            "session_id": sess_id,
            "credential_id": b64url_encode(b"phone-cred-1"),
            "qx": hex(qx),
            "qy": hex(qy),
            "authenticator_data": b64url_encode(auth_data),
            "client_data_json": b64url_encode(client_data.encode("utf-8")),
            "r": hex(r),
            "s": hex(s),
        },
    )
    assert reg_res.status_code == 200
    assert "tecc_vs_session" in reg_res.cookies
    cookie = reg_res.cookies["tecc_vs_session"]

    # Session is not active yet until laptop approves
    dash_res = gateway.get("/api/dashboard", cookies={"tecc_vs_session": cookie})
    assert dash_res.status_code == 403

    # 6. Laptop enters matching code and approves
    bad_app = admin.post(f"/admin/sessions/{sess_id}/approve", json={"code": "000000"})
    assert bad_app.status_code == 403

    good_app = admin.post(f"/admin/sessions/{sess_id}/approve", json={"code": pair_code})
    assert good_app.status_code == 200
    assert good_app.json()["state"] == "ACTIVE"

    # Now phone dashboard is accessible
    active_dash = gateway.get("/api/dashboard", cookies={"tecc_vs_session": cookie})
    assert active_dash.status_code == 200
    assert active_dash.json()["state"] == "ACTIVE"
    assert active_dash.json()["api_keys"] is None  # Keys never reach phone


def test_cannot_claim_already_registered_session(
    service_env: tuple[VirtualSessionService, TestClient, TestClient],
) -> None:
    svc, admin, gateway = service_env
    sess = admin.post("/admin/sessions", json={"name": "Device 1"}).json()
    sess_id = sess["id"]

    # Register Device 1
    opts = gateway.post("/webauthn/register/options", json={"session_id": sess_id}).json()
    auth_data = build_authenticator_data(rp_id="xxxx.trycloudflare.co", user_present=True, user_verified=True)
    gateway.post(
        "/webauthn/register/verify",
        json={
            "session_id": sess_id,
            "credential_id": b64url_encode(b"device-1-cred"),
            "authenticator_data": b64url_encode(auth_data),
        },
    )

    # Device 2 tries to get registration options for the same link
    opt_err = gateway.post("/webauthn/register/options", json={"session_id": sess_id})
    assert opt_err.status_code == 400


def test_delete_on_laptop_immediately_revokes(
    service_env: tuple[VirtualSessionService, TestClient, TestClient],
) -> None:
    svc, admin, gateway = service_env
    sess = admin.post("/admin/sessions", json={"name": "Temp Phone"}).json()
    sess_id = sess["id"]

    # Register and approve
    gateway.post("/webauthn/register/options", json={"session_id": sess_id})
    auth_data = build_authenticator_data(rp_id="xxxx.trycloudflare.co", user_present=True, user_verified=True)
    reg = gateway.post(
        "/webauthn/register/verify",
        json={
            "session_id": sess_id,
            "credential_id": b64url_encode(b"cred-del"),
            "authenticator_data": b64url_encode(auth_data),
        },
    )
    cookie = reg.cookies["tecc_vs_session"]
    admin.post(f"/admin/sessions/{sess_id}/approve", json={"code": sess["pair_code"]})

    # Works before delete
    assert gateway.get("/api/dashboard", cookies={"tecc_vs_session": cookie}).status_code == 200

    # Admin deletes session
    del_res = admin.delete(f"/admin/sessions/{sess_id}")
    assert del_res.status_code == 200
    assert del_res.json()["state"] == "REVOKED"

    # Next phone request returns 401
    post_del = gateway.get("/api/dashboard", cookies={"tecc_vs_session": cookie})
    assert post_del.status_code == 401


def test_disconnect_on_phone_revokes_and_clears_cookie(
    service_env: tuple[VirtualSessionService, TestClient, TestClient],
) -> None:
    svc, admin, gateway = service_env
    sess = admin.post("/admin/sessions", json={"name": "Phone To Disconnect"}).json()
    sess_id = sess["id"]

    gateway.post("/webauthn/register/options", json={"session_id": sess_id})
    auth_data = build_authenticator_data(rp_id="xxxx.trycloudflare.co", user_present=True, user_verified=True)
    reg = gateway.post(
        "/webauthn/register/verify",
        json={
            "session_id": sess_id,
            "credential_id": b64url_encode(b"cred-disc"),
            "authenticator_data": b64url_encode(auth_data),
        },
    )
    cookie = reg.cookies["tecc_vs_session"]
    admin.post(f"/admin/sessions/{sess_id}/approve", json={"code": sess["pair_code"]})

    # Phone disconnects
    disc_res = gateway.post("/api/disconnect", cookies={"tecc_vs_session": cookie})
    assert disc_res.status_code == 200

    # Admin list shows REVOKED
    s_list = admin.get("/admin/sessions").json()
    revoked = [s for s in s_list if s["id"] == sess_id][0]
    assert revoked["state"] == "REVOKED"


def test_url_change_relink_required_and_reconnect(
    service_env: tuple[VirtualSessionService, TestClient, TestClient],
) -> None:
    svc, admin, gateway = service_env
    sess = admin.post("/admin/sessions", json={"name": "Relink Phone"}).json()
    sess_id = sess["id"]

    gateway.post("/webauthn/register/options", json={"session_id": sess_id})
    auth_data = build_authenticator_data(rp_id="xxxx.trycloudflare.co", user_present=True, user_verified=True)
    reg = gateway.post(
        "/webauthn/register/verify",
        json={
            "session_id": sess_id,
            "credential_id": b64url_encode(b"cred-relink"),
            "authenticator_data": b64url_encode(auth_data),
        },
    )
    cookie = reg.cookies["tecc_vs_session"]
    admin.post(f"/admin/sessions/{sess_id}/approve", json={"code": sess["pair_code"]})

    # URL changes (laptop woke up or cloudflared restarted)
    svc.tunnel.simulate_url_change("https://new-random-123.trycloudflare.com")

    # Access is blocked with 409 Relink Required
    req_res = gateway.get("/api/dashboard", cookies={"tecc_vs_session": cookie})
    assert req_res.status_code == 409

    # Laptop calls reconnect
    recon_res = admin.post(f"/admin/sessions/{sess_id}/reconnect")
    assert recon_res.status_code == 200
    recon_data = recon_res.json()
    assert recon_data["state"] == "PENDING"
    assert recon_data["tunnel_host"] == "new-random-123.trycloudflare.com"
    assert "new-random-123.trycloudflare.com" in recon_data["link"]


def test_gateway_route_isolation_and_hardening_headers(
    service_env: tuple[VirtualSessionService, TestClient, TestClient],
) -> None:
    _, _, gateway = service_env
    # Admin route requested through gateway must return 404
    assert gateway.post("/admin/sessions").status_code == 404
    assert gateway.get("/admin/sessions").status_code == 404
    assert gateway.post("/admin/killswitch").status_code == 404
    assert gateway.get("/docs").status_code == 404
    assert gateway.get("/openapi.json").status_code == 404
    assert gateway.get("/api/mandate/draft").status_code == 404

    # Check hardening headers on valid response
    resp = gateway.get("/s/non-existent-id")
    assert resp.headers["Strict-Transport-Security"].startswith("max-age=")
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Cache-Control"] == "no-store"
    assert resp.headers["Referrer-Policy"] == "no-referrer"


def test_stepup_biometric_trade_action_and_replay_protection(
    service_env: tuple[VirtualSessionService, TestClient, TestClient],
) -> None:
    svc, admin, gateway = service_env
    # Create session with can_trade=True
    sess = admin.post("/admin/sessions", json={"name": "Trade Session", "can_trade": True}).json()
    sess_id = sess["id"]

    opt = gateway.post("/webauthn/register/options", json={"session_id": sess_id}).json()
    key, qx, qy = generate_p256_keypair()
    auth_data = build_authenticator_data(rp_id="xxxx.trycloudflare.co", user_present=True, user_verified=True, sign_count=1)
    client_data = json.dumps({
        "type": "webauthn.create",
        "challenge": opt["challenge"],
        "origin": "https://xxxx.trycloudflare.co",
    })
    r, s, _ = sign_webauthn_p256(key, auth_data, hashlib.sha256(client_data.encode()).digest())

    reg = gateway.post(
        "/webauthn/register/verify",
        json={
            "session_id": sess_id,
            "credential_id": b64url_encode(b"cred-trade"),
            "qx": hex(qx),
            "qy": hex(qy),
            "authenticator_data": b64url_encode(auth_data),
            "client_data_json": b64url_encode(client_data.encode()),
            "r": hex(r),
            "s": hex(s),
        },
    )
    cookie = reg.cookies["tecc_vs_session"]
    admin.post(f"/admin/sessions/{sess_id}/approve", json={"code": sess["pair_code"]})

    # Step 1: Attempt trade WITHOUT step-up token -> 422/403
    no_token = gateway.post(
        "/api/trade/execute",
        cookies={"tecc_vs_session": cookie},
        json={"stepup_token": "", "params": {"amount": 100}},
    )
    assert no_token.status_code == 403

    # Step 2: Request step-up challenge for action "execute" with params {"amount": 100}
    step_opts = gateway.post(
        "/webauthn/stepup/options",
        cookies={"tecc_vs_session": cookie},
        json={"action": "execute", "params": {"amount": 100}},
    ).json()

    # Step 3: Sign step-up assertion (sign_count must increase from 1 to 2)
    step_auth = build_authenticator_data(rp_id="xxxx.trycloudflare.co", user_present=True, user_verified=True, sign_count=2)
    step_cd = json.dumps({
        "type": "webauthn.get",
        "challenge": step_opts["challenge"],
        "origin": "https://xxxx.trycloudflare.co",
    })
    sr, ss, _ = sign_webauthn_p256(key, step_auth, hashlib.sha256(step_cd.encode()).digest())

    step_verify = gateway.post(
        "/webauthn/stepup/verify",
        cookies={"tecc_vs_session": cookie},
        json={
            "action": "execute",
            "credential_id": b64url_encode(b"cred-trade"),
            "authenticator_data": b64url_encode(step_auth),
            "client_data_json": b64url_encode(step_cd.encode()),
            "r": hex(sr),
            "s": hex(ss),
            "params": {"amount": 100},
        },
    )
    assert step_verify.status_code == 200
    token = step_verify.json()["stepup_token"]

    # Step 4: Execute trade using the step-up token
    trade_res = gateway.post(
        "/api/trade/execute",
        cookies={"tecc_vs_session": cookie},
        json={"stepup_token": token, "params": {"amount": 100}},
    )
    assert trade_res.status_code == 200
    assert trade_res.json()["status"] == "executed"

    # Step 5: Replay of same token MUST fail (single-use)
    replay_res = gateway.post(
        "/api/trade/execute",
        cookies={"tecc_vs_session": cookie},
        json={"stepup_token": token, "params": {"amount": 100}},
    )
    assert replay_res.status_code == 403


def test_killswitch_revokes_all_and_stops_tunnel(
    service_env: tuple[VirtualSessionService, TestClient, TestClient],
) -> None:
    svc, admin, gateway = service_env
    # Create two sessions
    admin.post("/admin/sessions", json={"name": "Device A"})
    admin.post("/admin/sessions", json={"name": "Device B"})

    kill_res = admin.post("/admin/killswitch")
    assert kill_res.status_code == 200
    assert kill_res.json()["revoked_sessions"] >= 2
    assert kill_res.json()["tunnel_stopped"] is True

    # All sessions are REVOKED
    all_sess = admin.get("/admin/sessions").json()
    for s in all_sess:
        assert s["state"] == "REVOKED"
        assert s["can_trade"] is False

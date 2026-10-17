"""Admin App Router (127.0.0.1:8000, NEVER tunneled) - Section 7.

Handles:
- POST /admin/sessions : Create session (ensures tunnel is up, returns link + QR)
- GET  /admin/sessions : List sessions (name, state, device, last seen, IP, country)
- POST /admin/sessions/{id}/approve : Approve pending pairing with 6-digit code
- POST /admin/sessions/{id}/reconnect : Reconnect a RELINK_REQUIRED session with fresh link
- DELETE /admin/sessions/{id} : Revoke and wipe session
- POST /admin/killswitch : Revoke all sessions and stop tunnel
- GET  /admin/audit : View audit trail
- GET  /admin/virtual-sessions : Full Laptop UI
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from tecc_brain.virtual_session.html_pages import render_laptop_admin_html
from tecc_brain.virtual_session.service import get_virtual_session_service

router = APIRouter(prefix="/admin", tags=["virtual_sessions_admin"])


class CreateSessionRequest(BaseModel):
    name: str = Field("My iPhone", max_length=64, description="Human-readable device/session name")
    can_trade: bool = Field(False, description="Whether phone is authorized to execute trades (defaults to read-only)")


class ApproveSessionRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, description="6-digit confirmation code shown on phone screen")


def _get_client_ip_country(request: Request) -> tuple[str, str]:
    ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "127.0.0.1")
    country = request.headers.get("cf-ipcountry", "LOCAL")
    return ip, country


@router.post("/sessions")
def create_session(req: CreateSessionRequest, request: Request) -> dict[str, Any]:
    """POST /admin/sessions: Create a session. Ensures tunnel is up and returns link and QR."""
    service = get_virtual_session_service()
    ip, country = _get_client_ip_country(request)
    session = service.create_session(
        name=req.name,
        can_trade=req.can_trade,
        ip=ip,
        country=country,
    )
    return session


@router.get("/sessions")
def list_sessions() -> list[dict[str, Any]]:
    """GET /admin/sessions: List sessions: name, state, device, last seen, IP and country."""
    service = get_virtual_session_service()
    return service.list_sessions()


@router.post("/sessions/{session_id}/approve")
def approve_session(session_id: str, req: ApproveSessionRequest, request: Request) -> dict[str, Any]:
    """POST /admin/sessions/{id}/approve: Approve a pending pairing (after the code matches)."""
    service = get_virtual_session_service()
    ip, country = _get_client_ip_country(request)
    try:
        return service.approve_session(session_id, req.code, ip=ip, country=country)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/sessions/{session_id}/reconnect")
def reconnect_session(session_id: str, request: Request) -> dict[str, Any]:
    """POST /admin/sessions/{id}/reconnect: Issue a new link for RELINK_REQUIRED."""
    service = get_virtual_session_service()
    ip, country = _get_client_ip_country(request)
    try:
        return service.reconnect_session(session_id, ip=ip, country=country)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: str, request: Request) -> dict[str, Any]:
    """DELETE /admin/sessions/{id}: Revoke and wipe."""
    service = get_virtual_session_service()
    ip, country = _get_client_ip_country(request)
    try:
        return service.revoke_session(session_id, reason="admin_delete", ip=ip, country=country)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")


@router.post("/killswitch")
def killswitch(request: Request) -> dict[str, Any]:
    """POST /admin/killswitch: Revoke everything and stop the tunnel."""
    service = get_virtual_session_service()
    ip, country = _get_client_ip_country(request)
    revoked_count = service.killswitch(ip=ip, country=country)
    return {"status": "ok", "revoked_sessions": revoked_count, "tunnel_stopped": True}


@router.get("/audit")
def get_audit_log() -> list[dict[str, Any]]:
    """GET /admin/audit: Audit log showing session creation, approval, logins, trades, revocations."""
    service = get_virtual_session_service()
    return service.db.list_audit_log(limit=200)


@router.get("/virtual-sessions", response_class=HTMLResponse)
def get_virtual_sessions_ui() -> str:
    """Section 8.4: Laptop UI ('Virtual Sessions' screen)."""
    service = get_virtual_session_service()
    sessions = service.list_sessions()
    audit = service.db.list_audit_log(limit=100)
    return render_laptop_admin_html(sessions, audit)

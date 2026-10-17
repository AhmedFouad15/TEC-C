"""Virtual Session Service Coordinator.

Ties together VirtualSessionDB, TunnelManager, and WebAuthnEngine.
"""

from __future__ import annotations

import os
from typing import Any

from tecc_brain.virtual_session.db import VirtualSessionDB, default_db_path
from tecc_brain.virtual_session.qr import render_qr_data_uri, render_qr_svg
from tecc_brain.virtual_session.tunnel import DEFAULT_TEMP_TUNNEL_URL, TunnelManager
from tecc_brain.virtual_session.webauthn_engine import (
    build_assertion_options,
    build_registration_options,
    compute_action_hash,
    compute_stepup_challenge,
    rp_config,
    verify_assertion_response,
    verify_registration_response,
)

_SERVICE: VirtualSessionService | None = None


class VirtualSessionService:
    """Core domain service for Virtual Sessions."""

    def __init__(
        self,
        db: VirtualSessionDB | None = None,
        tunnel: TunnelManager | None = None,
    ) -> None:
        self.db = db or VirtualSessionDB()
        self.tunnel = tunnel or TunnelManager()
        # Bind tunnel URL change callback
        self.tunnel.on_url_change = self._on_tunnel_url_changed

    def _on_tunnel_url_changed(self, old_url: str, new_url: str) -> None:
        from tecc_brain.virtual_session.tunnel import extract_hostname
        old_host = extract_hostname(old_url)
        new_host = extract_hostname(new_url)
        self.db.mark_relink_required_all(old_host, new_host)

    def create_session(
        self,
        name: str = "My iPhone",
        can_trade: bool = False,
        ip: str = "127.0.0.1",
        country: str = "LOCAL",
    ) -> dict[str, Any]:
        """Creates a session, ensuring tunnel is running, and returns link + QR code."""
        tunnel_url = self.tunnel.start()
        tunnel_host = self.tunnel.tunnel_host
        session = self.db.create_session(
            name=name,
            tunnel_host=tunnel_host,
            can_trade=can_trade,
            ip=ip,
            country=country,
        )
        link = f"{tunnel_url.rstrip('/')}/s/{session['id']}"
        session["link"] = link
        session["qr_svg"] = render_qr_svg(link)
        session["qr_data_uri"] = render_qr_data_uri(link)
        return session

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions = self.db.list_sessions()
        tunnel_url = self.tunnel.url or self.tunnel.default_url
        for s in sessions:
            s["link"] = f"{tunnel_url.rstrip('/')}/s/{s['id']}"
        return sessions

    def approve_session(
        self,
        session_id: str,
        pair_code: str,
        ip: str = "127.0.0.1",
        country: str = "LOCAL",
    ) -> dict[str, Any]:
        return self.db.approve_session(session_id, pair_code, ip, country)

    def reconnect_session(
        self,
        session_id: str,
        ip: str = "127.0.0.1",
        country: str = "LOCAL",
    ) -> dict[str, Any]:
        tunnel_url = self.tunnel.start()
        tunnel_host = self.tunnel.tunnel_host
        session = self.db.reconnect_session(session_id, tunnel_host, ip, country)
        link = f"{tunnel_url.rstrip('/')}/s/{session['id']}"
        session["link"] = link
        session["qr_svg"] = render_qr_svg(link)
        session["qr_data_uri"] = render_qr_data_uri(link)
        return session

    def revoke_session(
        self,
        session_id: str,
        reason: str = "admin_delete",
        ip: str = "127.0.0.1",
        country: str = "LOCAL",
    ) -> dict[str, Any]:
        return self.db.revoke_session(session_id, reason=reason, ip=ip, country=country)

    def killswitch(self, ip: str = "127.0.0.1", country: str = "LOCAL") -> int:
        revoked_count = self.db.killswitch_all(ip, country)
        self.tunnel.stop()
        return revoked_count

    # -------------------------------------------------------------------------
    # WebAuthn Flow Delegations
    # -------------------------------------------------------------------------

    def get_registration_options(self, session_id: str) -> dict[str, Any]:
        sess = self.db.get_session(session_id)
        if not sess:
            raise KeyError("Session not found")
        if sess["state"] != "PENDING":
            raise ValueError(f"Registration only available in PENDING state (current: {sess['state']})")
        if sess["has_credential"]:
            raise ValueError("Session already has a registered credential")

        challenge_id, challenge_bytes = self.db.create_challenge(session_id, purpose="register")
        return build_registration_options(sess, challenge_bytes, challenge_id)

    def verify_registration(
        self,
        session_id: str,
        credential_id_raw: str | bytes,
        qx: str | int,
        qy: str | int,
        authenticator_data_raw: str | bytes,
        client_data_json_raw: str | bytes | None = None,
        r: str | int | None = None,
        s: str | int | None = None,
        signature_raw: str | bytes | None = None,
        transports: list[str] | None = None,
        user_agent: str | None = None,
        ip: str = "127.0.0.1",
        country: str = "XX",
    ) -> tuple[dict[str, Any], str]:
        sess = self.db.get_session(session_id)
        if not sess:
            raise KeyError("Session not found")
        if sess["state"] != "PENDING":
            raise ValueError(f"Registration only available in PENDING state (current: {sess['state']})")

        challenge_data = self.db.consume_challenge(session_id, purpose="register")
        if not challenge_data:
            raise ValueError("Missing or expired registration challenge")

        verified = verify_registration_response(
            session=sess,
            expected_challenge=challenge_data["challenge"],
            credential_id_raw=credential_id_raw,
            qx=qx,
            qy=qy,
            authenticator_data_raw=authenticator_data_raw,
            client_data_json_raw=client_data_json_raw,
            r=r,
            s=s,
            signature_raw=signature_raw,
            transports=transports,
        )

        updated_sess = self.db.store_credential(
            session_id=session_id,
            credential_id=verified["credential_id"],
            qx=verified["qx"],
            qy=verified["qy"],
            sign_count=verified["sign_count"],
            transports=verified["transports"],
            user_agent=user_agent,
            ip=ip,
            country=country,
        )

        cookie_token = self.db.issue_cookie(session_id)
        return updated_sess, cookie_token

    def get_login_options(self, session_id: str) -> dict[str, Any]:
        sess = self.db.get_session(session_id)
        if not sess:
            raise KeyError("Session not found")
        if sess["state"] != "ACTIVE":
            raise ValueError(f"Login requires ACTIVE state (current: {sess['state']})")
        cred = self.db.get_credential(session_id)
        if not cred:
            raise ValueError("No credential registered for session")

        challenge_id, challenge_bytes = self.db.create_challenge(session_id, purpose="login")
        return build_assertion_options(
            sess,
            cred["credential_id"],
            challenge_bytes,
            challenge_id,
            purpose="login",
        )

    def verify_login(
        self,
        session_id: str,
        credential_id_raw: str | bytes,
        authenticator_data_raw: str | bytes,
        client_data_json_raw: str | bytes | None = None,
        r: str | int | None = None,
        s: str | int | None = None,
        signature_raw: str | bytes | None = None,
        ip: str = "127.0.0.1",
        country: str = "XX",
    ) -> tuple[dict[str, Any], str]:
        sess = self.db.get_session(session_id)
        if not sess:
            raise KeyError("Session not found")
        if sess["state"] != "ACTIVE":
            raise ValueError(f"Login requires ACTIVE state (current: {sess['state']})")
        cred = self.db.get_credential(session_id)
        if not cred:
            raise ValueError("No credential registered for session")

        challenge_data = self.db.consume_challenge(session_id, purpose="login")
        if not challenge_data:
            raise ValueError("Missing or expired login challenge")

        new_sign_count = verify_assertion_response(
            session=sess,
            stored_credential=cred,
            expected_challenge=challenge_data["challenge"],
            credential_id_raw=credential_id_raw,
            authenticator_data_raw=authenticator_data_raw,
            client_data_json_raw=client_data_json_raw,
            r=r,
            s=s,
            signature_raw=signature_raw,
        )

        self.db.update_sign_count(session_id, new_sign_count)
        self.db.update_touch(session_id, ip=ip, country=country)
        self.db.log_event(
            session_id=session_id,
            event="login_success",
            ip=ip,
            country=country,
            detail=f"sign_count={new_sign_count}",
        )
        cookie_token = self.db.issue_cookie(session_id)
        return self.db.get_session(session_id), cookie_token  # type: ignore[return-value]

    def get_stepup_options(
        self,
        session_id: str,
        action: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sess = self.db.get_session(session_id)
        if not sess or sess["state"] != "ACTIVE":
            raise ValueError("Step-up requires an ACTIVE session")
        cred = self.db.get_credential(session_id)
        if not cred:
            raise ValueError("No credential registered")

        action_hash = compute_action_hash(action, params)
        challenge_bytes = compute_stepup_challenge(action_hash)
        challenge_id, _ = self.db.create_challenge(
            session_id,
            purpose="stepup",
            challenge_bytes=challenge_bytes,
            action_hash=action_hash,
        )
        return build_assertion_options(
            sess,
            cred["credential_id"],
            challenge_bytes,
            challenge_id,
            purpose="stepup",
            action_hash=action_hash,
        )

    def verify_stepup(
        self,
        session_id: str,
        action: str,
        credential_id_raw: str | bytes,
        authenticator_data_raw: str | bytes,
        client_data_json_raw: str | bytes | None = None,
        r: str | int | None = None,
        s: str | int | None = None,
        signature_raw: str | bytes | None = None,
        params: dict[str, Any] | None = None,
        ip: str = "127.0.0.1",
        country: str = "XX",
    ) -> str:
        sess = self.db.get_session(session_id)
        if not sess or sess["state"] != "ACTIVE":
            raise ValueError("Step-up requires an ACTIVE session")
        cred = self.db.get_credential(session_id)
        if not cred:
            raise ValueError("No credential registered")

        expected_action_hash = compute_action_hash(action, params)
        challenge_data = self.db.consume_challenge(session_id, purpose="stepup")
        if not challenge_data:
            raise ValueError("Missing or expired step-up challenge")

        if not challenge_data.get("action_hash") or not (
            challenge_data["action_hash"] == expected_action_hash
        ):
            raise ValueError("Step-up challenge is not bound to this action")

        new_sign_count = verify_assertion_response(
            session=sess,
            stored_credential=cred,
            expected_challenge=challenge_data["challenge"],
            credential_id_raw=credential_id_raw,
            authenticator_data_raw=authenticator_data_raw,
            client_data_json_raw=client_data_json_raw,
            r=r,
            s=s,
            signature_raw=signature_raw,
        )

        self.db.update_sign_count(session_id, new_sign_count)
        stepup_token = self.db.issue_stepup_token(session_id, expected_action_hash)
        self.db.log_event(
            session_id=session_id,
            event="stepup_verified",
            ip=ip,
            country=country,
            detail=f"action={action} sign_count={new_sign_count}",
        )
        return stepup_token


def get_virtual_session_service() -> VirtualSessionService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = VirtualSessionService()
    return _SERVICE


def reset_virtual_session_service(service: VirtualSessionService | None = None) -> None:
    global _SERVICE
    _SERVICE = service

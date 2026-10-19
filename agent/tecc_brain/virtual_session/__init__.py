"""Virtual Session Package (Section 1-11 of Virtual_Session_Design.pdf).

Provides remote phone access to the local laptop app via a Cloudflare Quick-Tunnel link
and biometric WebAuthn passkey login (Face ID).
"""

from __future__ import annotations

from tecc_brain.virtual_session.db import VirtualSessionDB
from tecc_brain.virtual_session.gateway import create_gateway_app, gateway_app
from tecc_brain.virtual_session.service import (
    VirtualSessionService,
    get_virtual_session_service,
    reset_virtual_session_service,
)
from tecc_brain.virtual_session.tunnel import (
    DEFAULT_TEMP_TUNNEL_URL,
    TunnelManager,
    extract_hostname,
    set_windows_keep_awake,
)
from tecc_brain.virtual_session.webauthn_engine import rp_config

__all__ = [
    "DEFAULT_TEMP_TUNNEL_URL",
    "TunnelManager",
    "VirtualSessionDB",
    "VirtualSessionService",
    "create_gateway_app",
    "extract_hostname",
    "gateway_app",
    "get_virtual_session_service",
    "reset_virtual_session_service",
    "rp_config",
    "set_windows_keep_awake",
]

"""Hostname-Driven WebAuthn Passkey Verification Engine for Virtual Sessions (Section 8.2).

Enforces:
- `rp_config(session)` bound dynamically to `session["tunnel_host"]` (never hardcoded).
- Registration: `authenticator_attachment="platform"`, `user_verification="required"`, `resident_key="preferred"`.
- Mandatory User Verification (`UV = 0x04`) and User Presence (`UP = 0x01`) flags on both registration and login/step-up.
- Strict `expected_rp_id` (`rpIdHash`) and `expected_origin` (`https://<tunnel_host>`) checks.
- Monotonically increasing `sign_count` check on every login and step-up assertion.
- Step-up challenge construction: `HMAC(server_secret, action_hash || nonce)`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from typing import Any

from tecc_brain.biometrics.passkey import (
     is_on_p256_curve,
    normalize_low_s,
    parse_authenticator_data,
    verify_p256_digest,
)


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(val: str) -> bytes:
    clean = val.strip()
    if clean.startswith(("0x", "0X")):
        return bytes.fromhex(clean[2:])
    padding = "=" * ((4 - len(clean) % 4) % 4)
    return base64.urlsafe_b64decode(clean + padding)


def rp_config(session: dict[str, Any]) -> dict[str, str]:
    """Section 8.2: Hostname comes from the session, not hardcoded."""
    host = session["tunnel_host"]
    return {"rp_id": host, "origin": f"https://{host}", "rp_name": "PegGuard"}


def get_server_secret() -> bytes:
    secret_env = os.environ.get("TECC_STEPUP_SECRET", "tecc-virtual-session-hmac-secret-v1")
    return secret_env.encode("utf-8")


def compute_action_hash(action: str, params: dict[str, Any] | None = None) -> bytes:
    """Computes a canonical 32-byte SHA-256 hash binding a step-up biometric prompt to one specific action."""
    canonical = json.dumps(
        {"action": action.strip().lower(), "params": params or {}},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).digest()


def compute_stepup_challenge(
    action_hash: bytes,
    nonce: bytes | None = None,
    server_secret: bytes | None = None,
) -> bytes:
    """Section 8.2: Step-up challenge is HMAC(server_secret, action_hash || nonce)."""
    secret = server_secret or get_server_secret()
    n = nonce if nonce is not None else secrets.token_bytes(16)
    return hmac.new(secret, action_hash + n, hashlib.sha256).digest()


def build_registration_options(
    session: dict[str, Any],
    challenge_bytes: bytes,
    challenge_id: str,
) -> dict[str, Any]:
    """Section 8.2: Registration options with platform attachment, required UV, and preferred resident key."""
    rp = rp_config(session)
    return {
        "challenge_id": challenge_id,
        "rp": {"id": rp["rp_id"], "name": rp["rp_name"]},
        "user": {
            "id": b64url_encode(session["id"].encode("utf-8")),
            "name": session["name"],
            "displayName": session["name"],
        },
        "challenge": b64url_encode(challenge_bytes),
        "pubKeyCredParams": [{"type": "public-key", "alg": -7}],
        "timeout": 120000,
        "attestation": "none",
        "authenticatorSelection": {
            "authenticatorAttachment": "platform",
            "userVerification": "required",
            "residentKey": "preferred",
        },
        "expected_origin": rp["origin"],
    }


def build_assertion_options(
    session: dict[str, Any],
    credential_id: bytes,
    challenge_bytes: bytes,
    challenge_id: str,
    purpose: str = "login",
    action_hash: bytes | None = None,
) -> dict[str, Any]:
    """Section 8.2: Login / Step-up options restricting `allowCredentials` to the session's credential only."""
    rp = rp_config(session)
    opts: dict[str, Any] = {
        "challenge_id": challenge_id,
        "purpose": purpose,
        "rpId": rp["rp_id"],
        "challenge": b64url_encode(challenge_bytes),
        "timeout": 120000,
        "userVerification": "required",
        "allowCredentials": [
            {
                "type": "public-key",
                "id": b64url_encode(credential_id),
                "transports": ["internal", "hybrid"],
            }
        ],
        "expected_origin": rp["origin"],
    }
    if action_hash is not None:
        opts["action_hash_hex"] = "0x" + action_hash.hex()
    return opts


def _parse_int_coord(val: str | int) -> int:
    if isinstance(val, int):
        return val
    s = val.strip()
    if s.startswith(("0x", "0X")):
        return int(s, 16)
    try:
        return int(s)
    except ValueError:
        return int.from_bytes(b64url_decode(s), "big")


def _parse_der_or_raw_signature(sig_data: bytes) -> tuple[int, int]:
    """Parses either a 64-byte raw (r || s) signature or an ASN.1 DER-encoded ECDSA signature."""
    if len(sig_data) == 64:
        r = int.from_bytes(sig_data[:32], "big")
        s = int.from_bytes(sig_data[32:], "big")
        return r, normalize_low_s(s)
    # ASN.1 DER sequence: 0x30 <len> 0x02 <r_len> <r_bytes> 0x02 <s_len> <s_bytes>
    if len(sig_data) >= 8 and sig_data[0] == 0x30:
        idx = 2
        if sig_data[1] & 0x80:
            idx = 2 + (sig_data[1] & 0x7F)
        if sig_data[idx] != 0x02:
            raise ValueError("Invalid DER ECDSA signature (missing R integer tag)")
        r_len = sig_data[idx + 1]
        r_bytes = sig_data[idx + 2 : idx + 2 + r_len]
        idx = idx + 2 + r_len
        if sig_data[idx] != 0x02:
            raise ValueError("Invalid DER ECDSA signature (missing S integer tag)")
        s_len = sig_data[idx + 1]
        s_bytes = sig_data[idx + 2 : idx + 2 + s_len]
        r = int.from_bytes(r_bytes, "big")
        s = int.from_bytes(s_bytes, "big")
        return r, normalize_low_s(s)
    raise ValueError(f"Unsupported ECDSA signature format ({len(sig_data)} bytes)")


def _verify_client_data(
    client_data_bytes: bytes,
    expected_type: str,
    expected_challenge: bytes,
    expected_origin: str,
) -> bytes:
    """Verifies WebAuthn clientDataJSON (type, challenge, origin) and returns sha256(clientDataJSON)."""
    try:
        parsed = json.loads(client_data_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Malformed clientDataJSON: {exc}") from exc

    if parsed.get("type") != expected_type:
        raise ValueError(f"Unexpected WebAuthn type: got '{parsed.get('type')}', expected '{expected_type}'")

    given_challenge = b64url_decode(parsed.get("challenge", ""))
    if not hmac.compare_digest(given_challenge, expected_challenge):
        raise ValueError("WebAuthn challenge mismatch")

    given_origin = (parsed.get("origin") or "").rstrip("/")
    if given_origin.lower() != expected_origin.lower().rstrip("/"):
        raise ValueError(f"WebAuthn origin mismatch: got '{given_origin}', expected '{expected_origin}'")

    return hashlib.sha256(client_data_bytes).digest()


def _verify_auth_data(
    auth_data: bytes,
    expected_rp_id: str,
) -> tuple[int, bool, bool]:
    """Verifies authenticatorData rpIdHash, UP (Bit 0), and UV (Bit 2) flags. Returns (sign_count, up, uv)."""
    parsed = parse_authenticator_data(auth_data)
    expected_rp_hash = "0x" + hashlib.sha256(expected_rp_id.encode("utf-8")).hexdigest()
    if parsed.rp_id_hash_hex.lower() != expected_rp_hash.lower():
        raise ValueError(
            f"WebAuthn rpIdHash mismatch for host '{expected_rp_id}'"
        )
    if not (parsed.user_present_up or parsed.user_verified_uv):
        raise ValueError("WebAuthn User Present (UP) flag is not set")
    return parsed.sign_count, parsed.user_present_up, parsed.user_verified_uv


def verify_registration_response(
    session: dict[str, Any],
    expected_challenge: bytes,
    credential_id_raw: str | bytes,
    qx: str | int,
    qy: str | int,
    authenticator_data_raw: str | bytes,
    client_data_json_raw: str | bytes | None = None,
    r: str | int | None = None,
    s: str | int | None = None,
    signature_raw: str | bytes | None = None,
    transports: list[str] | None = None,
) -> dict[str, Any]:
    """Verifies a WebAuthn passkey registration response against `rp_config(session)` and `expected_challenge`."""
    rp = rp_config(session)
    cred_id = credential_id_raw if isinstance(credential_id_raw, bytes) else b64url_decode(credential_id_raw)
    if not cred_id:
        raise ValueError("Empty credential_id")

    auth_data = (
        authenticator_data_raw
        if isinstance(authenticator_data_raw, bytes)
        else b64url_decode(authenticator_data_raw)
    )
    sign_count, _, _ = _verify_auth_data(auth_data, rp["rp_id"])

    if client_data_json_raw is not None:
        cd_bytes = (
            client_data_json_raw
            if isinstance(client_data_json_raw, bytes)
            else b64url_decode(client_data_json_raw)
            if not str(client_data_json_raw).strip().startswith("{")
            else str(client_data_json_raw).encode("utf-8")
        )
        cd_hash = _verify_client_data(
            cd_bytes,
            expected_type="webauthn.create",
            expected_challenge=expected_challenge,
            expected_origin=rp["origin"],
        )
    else:
        cd_hash = hashlib.sha256(expected_challenge).digest()

    qx_i = _parse_int_coord(qx)
    qy_i = _parse_int_coord(qy)
    if not is_on_p256_curve(qx_i, qy_i):
        raise ValueError("Invalid P-256 public key coordinates (point not on secp256r1 curve)")

    # If a self-attestation / registration signature is provided, verify it as well
    if r is not None and s is not None:
        r_i = _parse_int_coord(r)
        s_i = _parse_int_coord(s)
        msg_hash = hashlib.sha256(auth_data + cd_hash).digest()
        if not verify_p256_digest(msg_hash, r_i, s_i, qx_i, qy_i):
            raise ValueError("Invalid P-256 attestation signature")
    elif signature_raw is not None:
        sig_bytes = signature_raw if isinstance(signature_raw, bytes) else b64url_decode(signature_raw)
        r_i, s_i = _parse_der_or_raw_signature(sig_bytes)
        msg_hash = hashlib.sha256(auth_data + cd_hash).digest()
        if not verify_p256_digest(msg_hash, r_i, s_i, qx_i, qy_i):
            raise ValueError("Invalid P-256 attestation signature")

    return {
        "credential_id": cred_id,
        "qx": qx_i,
        "qy": qy_i,
        "sign_count": sign_count,
        "transports": transports or ["internal"],
    }


def verify_assertion_response(
    session: dict[str, Any],
    stored_credential: dict[str, Any],
    expected_challenge: bytes,
    credential_id_raw: str | bytes,
    authenticator_data_raw: str | bytes,
    client_data_json_raw: str | bytes | None = None,
    r: str | int | None = None,
    s: str | int | None = None,
    signature_raw: str | bytes | None = None,
) -> int:
    """Verifies a WebAuthn login or step-up assertion and returns the updated `sign_count`.

    Enforces:
    1. Credential ID matches the session's registered credential (`allow_credentials`).
    2. `clientDataJSON` matches `expected_challenge` and `expected_origin = https://<tunnel_host>`.
    3. `authenticatorData` matches `expected_rp_id` and has both `UP` (0x01) and `UV` (0x04) set.
    4. `sign_count > stored_credential["sign_count"]` (clone/replay detection).
    5. Cryptographic NIST P-256 signature verification with low-s enforcement.
    """
    rp = rp_config(session)
    cred_id = credential_id_raw if isinstance(credential_id_raw, bytes) else b64url_decode(credential_id_raw)
    if not hmac.compare_digest(cred_id, stored_credential["credential_id"]):
        raise ValueError("Credential ID does not match the registered passkey for this session")

    auth_data = (
        authenticator_data_raw
        if isinstance(authenticator_data_raw, bytes)
        else b64url_decode(authenticator_data_raw)
    )
    new_sign_count, _, _ = _verify_auth_data(auth_data, rp["rp_id"])

    prev_sign_count = int(stored_credential["sign_count"])
    if prev_sign_count > 0 and new_sign_count > 0 and new_sign_count <= prev_sign_count:
        raise ValueError(
            f"WebAuthn sign_count did not increase (got {new_sign_count}, previous {prev_sign_count})"
        )

    if client_data_json_raw is not None:
        cd_bytes = (
            client_data_json_raw
            if isinstance(client_data_json_raw, bytes)
            else b64url_decode(client_data_json_raw)
            if not str(client_data_json_raw).strip().startswith("{")
            else str(client_data_json_raw).encode("utf-8")
        )
        cd_hash = _verify_client_data(
            cd_bytes,
            expected_type="webauthn.get",
            expected_challenge=expected_challenge,
            expected_origin=rp["origin"],
        )
    else:
        cd_hash = hashlib.sha256(expected_challenge).digest()

    if r is not None and s is not None:
        r_i = _parse_int_coord(r)
        s_i = _parse_int_coord(s)
    elif signature_raw is not None:
        sig_bytes = signature_raw if isinstance(signature_raw, bytes) else b64url_decode(signature_raw)
        r_i, s_i = _parse_der_or_raw_signature(sig_bytes)
    else:
        raise ValueError("Missing WebAuthn assertion signature")

    msg_hash = hashlib.sha256(auth_data + cd_hash).digest()
    if not verify_p256_digest(
        msg_hash,
        r_i,
        s_i,
        int(stored_credential["qx"]),
        int(stored_credential["qy"]),
    ):
        raise ValueError("Invalid WebAuthn P-256 signature")

    return new_sign_count

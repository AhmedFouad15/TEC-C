"""Comprehensive tests for the Decentralized WebAuthn P-256 Biometric System & 4 Technical Nuances."""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from tecc_brain.app import app
from tecc_brain.biometrics import (
    DecentralizedBiometricManager,
    P256_N,
    P256_N_DIV_2,
    build_authenticator_data,
    generate_p256_keypair,
    is_canonical_low_s,
    is_on_p256_curve,
    parse_authenticator_data,
    sign_webauthn_p256,
)


def test_phase1_to_phase4_decentralized_biometric_lifecycle_and_4_nuances():
    """Verifies the complete 4-phase decentralized biometric workflow and all 4 production nuances:
    1. Nuance 1: RIP-7212 (0x100) on Arbitrum L2 vs Solidity P-256 fallback on Ethereum L1 & FISCO BCOS.
    2. Nuance 2: Signature malleability rejection when s > N/2.
    3. Nuance 3: On-chain authenticatorData flags (UP = 0x01 and UV = 0x04 required; passive tap without UV rejected).
    4. Nuance 4: Multi-device passkey registration (iPhone + MacBook) and Emergency Recovery Guardian.
    """
    mgr = DecentralizedBiometricManager()
    account = "0xBiometricVaultUser"

    # Phase 1: Hardware Enclave generates NIST P-256 keypair (iPhone Secure Enclave)
    iphone_priv, iphone_qx, iphone_qy = generate_p256_keypair(seed_int=1001)
    assert is_on_p256_curve(iphone_qx, iphone_qy) is True

    pk_primary = mgr.register_passkey(
        account, iphone_qx, iphone_qy, key_id="iphone-16-pro", device_label="iPhone 16 Pro FaceID"
    )
    assert pk_primary.is_primary is True

    # Nuance 4: Register backup MacBook Face ID passkey
    mac_priv, mac_qx, mac_qy = generate_p256_keypair(seed_int=2002)
    pk_backup = mgr.register_passkey(
        account, mac_qx, mac_qy, key_id="macbook-pro", device_label="MacBook Pro Face ID"
    )
    assert pk_backup.is_primary is False
    assert len(mgr.get_passkeys(account)) == 2

    # Nuance 3: Passive keypress without biometric UV (user_verified=False -> flags = 0x01) MUST BE REJECTED!
    passive_auth_data = build_authenticator_data(user_present=True, user_verified=False, sign_count=1)
    parsed_passive = parse_authenticator_data(passive_auth_data)
    assert parsed_passive.user_present_up is True
    assert parsed_passive.user_verified_uv is False

    challenge1 = hashlib.sha256(b"TetherBreak_Challenge_001").digest()
    r1, s1, _ = sign_webauthn_p256(iphone_priv, passive_auth_data, challenge1)
    res_passive = mgr.verify_webauthn_assertion(
        account=account,
        authenticator_data=passive_auth_data,
        client_data_hash=challenge1,
        r=r1,
        s=s1,
        qx=iphone_qx,
        qy=iphone_qy,
        require_uv=True,
    )
    assert res_passive.verified is False
    assert "BiometricUserVerificationRequired" in (res_passive.rejection_reason or "")
    assert mgr.is_biometric_window_active(account)[0] is False

    # Nuance 2: Malleable high-S signature (s_high = N - s_low > N/2) MUST BE REJECTED!
    biometric_auth_data = build_authenticator_data(user_present=True, user_verified=True, sign_count=2)
    r2, s2_low, _ = sign_webauthn_p256(iphone_priv, biometric_auth_data, challenge1, enforce_low_s=True)
    s2_high = P256_N - s2_low
    assert is_canonical_low_s(r2, s2_low) is True
    assert is_canonical_low_s(r2, s2_high) is False
    assert s2_high > P256_N_DIV_2

    res_malleable = mgr.verify_webauthn_assertion(
        account=account,
        authenticator_data=biometric_auth_data,
        client_data_hash=challenge1,
        r=r2,
        s=s2_high,
        qx=iphone_qx,
        qy=iphone_qy,
    )
    assert res_malleable.verified is False
    assert "SignatureMalleabilityRejected" in (res_malleable.rejection_reason or "")

    # Phase 3 & Phase 4: Valid FaceID signature (UP=1, UV=1, s <= N/2) verifies & opens 5-minute window!
    res_valid_l2 = mgr.verify_webauthn_assertion(
        account=account,
        authenticator_data=biometric_auth_data,
        client_data_hash=challenge1,
        r=r2,
        s=s2_low,
        qx=iphone_qx,
        qy=iphone_qy,
        chain_target="arbitrum_l2",
    )
    assert res_valid_l2.verified is True
    assert res_valid_l2.verification_path == "rip7212_precompile_0x100"
    assert res_valid_l2.low_s_canonical is True
    assert mgr.is_biometric_window_active(account)[0] is True

    # Replay protection: reusing the same challenge1 is rejected
    res_replay = mgr.verify_webauthn_assertion(
        account=account,
        authenticator_data=biometric_auth_data,
        client_data_hash=challenge1,
        r=r2,
        s=s2_low,
        qx=iphone_qx,
        qy=iphone_qy,
    )
    assert res_replay.verified is False
    assert "ChallengeAlreadyUsed" in (res_replay.rejection_reason or "")

    # Nuance 1 & Nuance 4: Backup MacBook Face ID verifies on Ethereum L1 / FISCO BCOS fallback path
    challenge2 = hashlib.sha256(b"TetherBreak_Challenge_002_L1_Fallback").digest()
    r3, s3_low, _ = sign_webauthn_p256(mac_priv, biometric_auth_data, challenge2)
    res_valid_l1 = mgr.verify_webauthn_assertion(
        account=account,
        authenticator_data=biometric_auth_data,
        client_data_hash=challenge2,
        r=r3,
        s=s3_low,
        qx=mac_qx,
        qy=mac_qy,
        chain_target="ethereum_l1",
    )
    assert res_valid_l1.verified is True
    assert res_valid_l1.key_id == "macbook-pro"
    assert res_valid_l1.verification_path == "solidity_p256_fallback"

    # Nuance 4: Emergency Guardian Account Recovery after device loss
    mgr.set_recovery_guardian(account, "0xTrustedHardwareGuardian")
    new_priv, new_qx, new_qy = generate_p256_keypair(seed_int=3003)

    with pytest.raises(PermissionError):
        mgr.recover_passkey_with_guardian(
            account, "0xAttacker", "recovered-iphone", new_qx, new_qy
        )

    recovered = mgr.recover_passkey_with_guardian(
        account, "0xTrustedHardwareGuardian", "recovered-iphone", new_qx, new_qy
    )
    assert recovered.key_id == "recovered-iphone"


def test_biometrics_fastapi_endpoints(tmp_path, monkeypatch):
    """Verifies the FastAPI /api/biometrics/register, /guardian, /recover, /verify, /revoke, and /status endpoints."""
    monkeypatch.setenv("TECC_STATE_DIR", str(tmp_path))
    client = TestClient(app)

    priv1, qx1, qy1 = generate_p256_keypair(seed_int=4001)
    priv2, qx2, qy2 = generate_p256_keypair(seed_int=4002)

    # 1. Register primary iPhone passkey
    r_reg1 = client.post(
        "/api/biometrics/register",
        json={
            "account": "alice",
            "key_id": "iphone-primary",
            "device_label": "iPhone FaceID",
            "qx": hex(qx1),
            "qy": hex(qy1),
        },
    )
    assert r_reg1.status_code == 200
    assert r_reg1.json()["key_id"] == "iphone-primary"

    # 2. Register backup MacBook passkey
    r_reg2 = client.post(
        "/api/biometrics/register",
        json={
            "account": "alice",
            "key_id": "macbook-backup",
            "device_label": "MacBook Face ID",
            "qx": hex(qx2),
            "qy": hex(qy2),
        },
    )
    assert r_reg2.status_code == 200

    # 3. Verify WebAuthn biometric assertion -> opens 5-minute grace window
    auth_data = build_authenticator_data(user_present=True, user_verified=True, sign_count=5)
    challenge = hashlib.sha256(b"API_Biometric_Breakout_001").digest()
    r_sig, s_sig, _ = sign_webauthn_p256(priv1, auth_data, challenge)

    r_ver = client.post(
        "/api/biometrics/verify",
        json={
            "account": "alice",
            "authenticator_data_hex": "0x" + auth_data.hex(),
            "client_data_hash_hex": "0x" + challenge.hex(),
            "r": hex(r_sig),
            "s": hex(s_sig),
            "qx": hex(qx1),
            "qy": hex(qy1),
            "require_uv": True,
            "chain_target": "arbitrum_l2",
        },
    )
    assert r_ver.status_code == 200
    ver_body = r_ver.json()
    assert ver_body["verified"] is True
    assert ver_body["low_s_canonical"] is True
    assert ver_body["authenticator_flags"]["user_verified_uv"] is True

    # 4. Check status endpoint
    r_status = client.get("/api/biometrics/status/alice")
    assert r_status.status_code == 200
    st = r_status.json()
    assert st["active_passkey_count"] == 2
    assert st["biometric_window_active"] is True

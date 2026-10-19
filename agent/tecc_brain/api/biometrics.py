"""/api/biometrics/*: Decentralized WebAuthn Passkey (NIST P-256) Biometric Registration, Verification & Recovery API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tecc_brain.api.deps import Account
from tecc_brain.biometrics import (
    BiometricVerificationResult,
    DecentralizedBiometricManager,
    RegisteredPasskey,
)

router = APIRouter(prefix="/api/biometrics", tags=["biometrics"])

_MANAGER: DecentralizedBiometricManager | None = None


def get_biometric_manager() -> DecentralizedBiometricManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = DecentralizedBiometricManager()
    return _MANAGER


class RegisterPasskeyRequest(BaseModel):
    account: Account = Field("demo", description="Smart account identifier")
    key_id: str = Field("primary", min_length=1, max_length=128, description="Unique device passkey identifier")
    device_label: str = Field("Primary Passkey", max_length=128, description="Device label (e.g. iPhone 16 Pro / MacBook)")
    qx: str = Field(description="Hex-encoded 32-byte affine X coordinate on secp256r1")
    qy: str = Field(description="Hex-encoded 32-byte affine Y coordinate on secp256r1")


class RevokePasskeyRequest(BaseModel):
    account: Account = Field("demo")
    key_id: str = Field(min_length=1, max_length=128)


class SetGuardianRequest(BaseModel):
    account: Account = Field("demo")
    guardian: str = Field(min_length=3, max_length=128, description="Emergency recovery guardian address")


class RecoverPasskeyRequest(BaseModel):
    account: Account = Field("demo")
    caller_guardian: str = Field(min_length=3, max_length=128)
    new_key_id: str = Field("recovered-device", min_length=1, max_length=128)
    device_label: str = Field("Recovered Device Passkey", max_length=128)
    new_qx: str = Field(description="Hex-encoded 32-byte affine X coordinate on secp256r1")
    new_qy: str = Field(description="Hex-encoded 32-byte affine Y coordinate on secp256r1")


class VerifyWebAuthnRequest(BaseModel):
    account: Account = Field("demo")
    authenticator_data_hex: str = Field(description="Hex-encoded WebAuthn authenticatorData (>= 37 bytes)")
    client_data_hash_hex: str = Field(description="Hex-encoded 32-byte SHA-256 clientDataJSON / challenge hash")
    r: str = Field(description="Hex or decimal P-256 signature R component")
    s: str = Field(description="Hex or decimal P-256 signature S component (must satisfy s <= N/2)")
    qx: str = Field(description="Hex or decimal P-256 public key X coordinate")
    qy: str = Field(description="Hex or decimal P-256 public key Y coordinate")
    require_uv: bool = Field(False, description="Enforce Bit 2 (UV = 0x04) biometric Face ID verification if available")
    chain_target: Literal["arbitrum_l2", "ethereum_l1", "fisco_bcos"] = Field(
        "arbitrum_l2",
        description="Target chain (Arbitrum L2 uses RIP-7212 0x100 precompile; Ethereum L1 & FISCO BCOS use Solidity fallback)",
    )


class BiometricAccountStatusResponse(BaseModel):
    account: str
    passkeys: list[RegisteredPasskey]
    active_passkey_count: int
    recovery_guardian: str | None = None
    biometric_window_active: bool
    biometric_window_valid_until: datetime | None = None


def _decode_hex_bytes(hex_str: str, field_name: str) -> bytes:
    clean = hex_str.strip()
    if clean.startswith(("0x", "0X")):
        clean = clean[2:]
    try:
        return bytes.fromhex(clean)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid hex in {field_name}: {exc}") from exc


@router.post("/register", response_model=RegisteredPasskey)
def register_passkey(req: RegisterPasskeyRequest) -> RegisteredPasskey:
    """Registers a primary or backup hardware WebAuthn P-256 passkey on-chain/off-chain."""
    mgr = get_biometric_manager()
    try:
        return mgr.register_passkey(
            account=req.account,
            qx=req.qx,
            qy=req.qy,
            key_id=req.key_id,
            device_label=req.device_label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/revoke", response_model=BiometricAccountStatusResponse)
def revoke_passkey(req: RevokePasskeyRequest) -> BiometricAccountStatusResponse:
    """Revokes a specific device passkey while ensuring at least one passkey remains active."""
    mgr = get_biometric_manager()
    try:
        mgr.revoke_passkey(req.account, req.key_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_status(req.account)


@router.post("/guardian", response_model=BiometricAccountStatusResponse)
def set_guardian(req: SetGuardianRequest) -> BiometricAccountStatusResponse:
    """Configures an Emergency Passkey Recovery Guardian for device-loss recovery."""
    mgr = get_biometric_manager()
    try:
        mgr.set_recovery_guardian(req.account, req.guardian)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return get_status(req.account)


@router.post("/recover", response_model=RegisteredPasskey)
def recover_passkey(req: RecoverPasskeyRequest) -> RegisteredPasskey:
    """Executes guardian-authorized passkey recovery when the user's primary device is lost."""
    mgr = get_biometric_manager()
    try:
        return mgr.recover_passkey_with_guardian(
            account=req.account,
            caller_guardian=req.caller_guardian,
            new_key_id=req.new_key_id,
            new_qx=req.new_qx,
            new_qy=req.new_qy,
            device_label=req.device_label,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/verify", response_model=BiometricVerificationResult)
def verify_biometrics(req: VerifyWebAuthnRequest) -> BiometricVerificationResult:
    """Verifies a hardware WebAuthn P-256 assertion (enforcing UP + UV flags and s <= N/2) and opens the 5-minute grace window."""
    mgr = get_biometric_manager()
    auth_bytes = _decode_hex_bytes(req.authenticator_data_hex, "authenticator_data_hex")
    cd_hash = _decode_hex_bytes(req.client_data_hash_hex, "client_data_hash_hex")
    if len(cd_hash) != 32:
        raise HTTPException(status_code=422, detail="client_data_hash_hex must be exactly 32 bytes")

    return mgr.verify_webauthn_assertion(
        account=req.account,
        authenticator_data=auth_bytes,
        client_data_hash=cd_hash,
        r=req.r,
        s=req.s,
        qx=req.qx,
        qy=req.qy,
        require_uv=req.require_uv,
        chain_target=req.chain_target,
    )


@router.get("/status/{account}", response_model=BiometricAccountStatusResponse)
def get_status(account: Account) -> BiometricAccountStatusResponse:
    """Returns registered device passkeys, recovery guardian, and 5-minute biometric grace window status."""
    mgr = get_biometric_manager()
    pks = mgr.get_passkeys(account)
    active, until = mgr.is_biometric_window_active(account)
    return BiometricAccountStatusResponse(
        account=account,
        passkeys=pks,
        active_passkey_count=len(pks),
        recovery_guardian=mgr.get_recovery_guardian(account),
        biometric_window_active=active,
        biometric_window_valid_until=until,
    )


class PinUnlockRequest(BaseModel):
    account: Account = "demo"
    pin: str = Field(min_length=4, max_length=32)


@router.post("/pin/unlock", response_model=BiometricVerificationResult)
def pin_unlock(req: PinUnlockRequest) -> BiometricVerificationResult:
    """Unlocks the 5-minute biometric window using the verified Security PIN."""
    from tecc_brain.security_pin import is_pin_configured, verify_pin
    if not is_pin_configured():
        raise HTTPException(status_code=400, detail="Security PIN is not configured yet. Configure it in Settings.")
    if not verify_pin(req.pin):
        raise HTTPException(status_code=401, detail="Invalid Security PIN")

    mgr = get_biometric_manager()
    mgr.open_biometric_window(req.account)
    from tecc_brain.api.vault import open_live_biometric_window
    open_live_biometric_window(req.account)

    return BiometricVerificationResult(
        account=req.account,
        verified=True,
        verification_path="pin_fallback",
        chain_target="arbitrum_l2",
    )

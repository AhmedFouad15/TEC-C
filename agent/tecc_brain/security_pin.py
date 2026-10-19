"""Security PIN Authenticator for System & Virtual Sessions (Section 8.5).

Provides a secure hardware/system PIN fallback for devices without registered biometrics
or where device-level biometric setup / Windows Hello PIN is unavailable.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

PIN_FILE = Path(__file__).resolve().parents[2] / ".state" / "security_pin.json"


def _ensure_dir() -> None:
    PIN_FILE.parent.mkdir(parents=True, exist_ok=True)


def is_pin_configured() -> bool:
    return PIN_FILE.is_file()


def get_pin_info() -> dict[str, Any]:
    if not PIN_FILE.is_file():
        return {"configured": False, "configured_at": None}
    try:
        data = json.loads(PIN_FILE.read_text(encoding="utf-8"))
        return {
            "configured": True,
            "configured_at": data.get("configured_at"),
            "last_used_at": data.get("last_used_at"),
        }
    except Exception:
        return {"configured": False, "configured_at": None}


def set_pin(pin: str) -> None:
    pin = pin.strip()
    if len(pin) < 4 or len(pin) > 32:
        raise ValueError("PIN must be between 4 and 32 characters.")
    _ensure_dir()
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256(f"{salt}:{pin}".encode("utf-8")).hexdigest()
    data = {
        "salt": salt,
        "hash": hashed,
        "configured_at": time.time(),
        "last_used_at": None,
    }
    PIN_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def verify_pin(pin: str) -> bool:
    if not PIN_FILE.is_file():
        return False
    try:
        data = json.loads(PIN_FILE.read_text(encoding="utf-8"))
        salt = data.get("salt", "")
        expected = data.get("hash", "")
        actual = hashlib.sha256(f"{salt}:{pin.strip()}".encode("utf-8")).hexdigest()
        if hmac.compare_digest(expected, actual):
            data["last_used_at"] = time.time()
            try:
                PIN_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception:
                pass
            return True
    except Exception:
        pass
    return False


def remove_pin() -> bool:
    if PIN_FILE.is_file():
        try:
            PIN_FILE.unlink()
            return True
        except Exception:
            return False
    return False

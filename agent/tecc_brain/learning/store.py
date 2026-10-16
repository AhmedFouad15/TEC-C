"""Local JSON persistence for learned profiles, one file per account. Profiles never leave the machine."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from tecc_brain.learning.update import new_profile
from tecc_brain.models import BrainProfile, RiskTier

_ADDRESS = re.compile(r"0x[0-9a-f]{40}")
_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}")
DEFAULT_STATE_DIR = Path(__file__).resolve().parents[2] / ".state"


def account_key(account: str) -> str:
    """Validated, normalised account id (also used to validate API input)."""
    if account.lower().startswith("0x"):
        key = account.lower()
        valid = _ADDRESS.fullmatch(key)  # anything that looks like an address must be a full one
    else:
        key = account.lower()  # one file per account even on case-insensitive filesystems
        valid = _NAME.fullmatch(key)
    if not valid:
        raise ValueError("account must be a 0x address or 1-64 letters, digits, '_' or '-'")
    return key


class ProfileStore:
    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            root = Path(os.environ.get("TECC_STATE_DIR", DEFAULT_STATE_DIR)) / "profiles"
        self.root = Path(root)

    def _path(self, account: str) -> Path:
        return self.root / f"{account_key(account)}.json"

    def load(self, account: str) -> BrainProfile | None:
        path = self._path(account)
        if not path.exists():
            return None
        return BrainProfile.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, profile: BrainProfile) -> None:
        path = self._path(profile.account)
        self.root.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.root, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(profile.model_dump_json(indent=2))
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def get_or_create(self, account: str, tier: RiskTier) -> BrainProfile:
        existing = self.load(account)
        if existing is not None:
            return existing
        profile = new_profile(account, tier)
        self.save(profile)
        return profile

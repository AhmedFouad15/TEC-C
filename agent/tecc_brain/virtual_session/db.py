"""SQLite Data Model & Persistence for Virtual Sessions (Section 6).

Implements the exact SQLite schema specified in Section 6 of Virtual_Session_Design.pdf:
  - `sessions`    : Persistent server-side sessions (no TTL; ends only on Delete or Disconnect)
  - `credentials` : Bound WebAuthn passkey credentials (credential_id, public_key, sign_count, transports)
  - `cookies`     : SHA-256 hashed 256-bit random session cookies bound to the session
  - `challenges`  : Short-lived (~2 minute), single-use WebAuthn challenges (register | login | stepup)
  - `audit_log`   : Immutable event trail (ts, session_id, event, ip, country, detail)
  - `stepup_tokens`: Single-use 60-second step-up authorization tokens bound to a specific action_hash
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Literal

SessionState = Literal["PENDING", "ACTIVE", "RELINK_REQUIRED", "REVOKED"]
ChallengePurpose = Literal["register", "login", "stepup"]

CHALLENGE_TTL_SECONDS = 120  # Section 6: ~2 minutes for one-time WebAuthn challenges
STEPUP_TOKEN_TTL_SECONDS = 60  # Section 5.5 & 8.2: 60-second single-use step-up token

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    state TEXT NOT NULL,
    tunnel_host TEXT NOT NULL,
    pair_code TEXT,
    can_trade INTEGER DEFAULT 0,
    created_at INTEGER NOT NULL,
    approved_at INTEGER,
    last_seen_at INTEGER,
    last_ip TEXT,
    last_country TEXT,
    user_agent TEXT
);

CREATE TABLE IF NOT EXISTS credentials (
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    credential_id BLOB PRIMARY KEY,
    public_key BLOB NOT NULL,
    sign_count INTEGER NOT NULL,
    transports TEXT
);

CREATE TABLE IF NOT EXISTS cookies (
    token_hash BLOB PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS challenges (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    purpose TEXT,
    challenge BLOB NOT NULL,
    action_hash BLOB,
    expires_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    ts INTEGER,
    session_id TEXT,
    event TEXT,
    ip TEXT,
    country TEXT,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS stepup_tokens (
    token_hash BLOB PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    action_hash BLOB NOT NULL,
    expires_at INTEGER NOT NULL
);
"""


def default_db_path() -> str:
    env_path = os.environ.get("TECC_VIRTUAL_SESSION_DB")
    if env_path:
        return env_path
    base_dir = Path(__file__).resolve().parents[2] / ".tecc_data"
    base_dir.mkdir(parents=True, exist_ok=True)
    return str(base_dir / "virtual_sessions.sqlite3")


class VirtualSessionDB:
    """Thread-safe SQLite repository for Virtual Sessions, Credentials, Cookies, Challenges, and Audit Logs."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or default_db_path()
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA_SQL)
            self._conn.commit()

    def _now(self) -> int:
        return int(time.time())

    # -------------------------------------------------------------------------
    # Sessions
    # -------------------------------------------------------------------------

    def create_session(
        self,
        name: str,
        tunnel_host: str,
        can_trade: bool = False,
        ip: str = "127.0.0.1",
        country: str = "LOCAL",
    ) -> dict[str, Any]:
        """Creates a new PENDING session with a 128-bit random ID and 6-digit pairing code."""
        session_id = secrets.token_hex(16)  # 128-bit random hex
        pair_code = f"{secrets.randbelow(1_000_000):06d}"
        now = self._now()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sessions (
                    id, name, state, tunnel_host, pair_code, can_trade,
                    created_at, approved_at, last_seen_at, last_ip, last_country, user_agent
                ) VALUES (?, ?, 'PENDING', ?, ?, ?, ?, NULL, ?, ?, ?, NULL)
                """,
                (session_id, name, tunnel_host, pair_code, int(bool(can_trade)), now, now, ip, country),
            )
            self._log_event_unlocked(
                session_id=session_id,
                event="session_created",
                ip=ip,
                country=country,
                detail=f"name={name} tunnel_host={tunnel_host} can_trade={int(bool(can_trade))}",
            )
            self._conn.commit()
        return self.get_session(session_id)  # type: ignore[return-value]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                return None
            cred = self._conn.execute(
                "SELECT credential_id, sign_count, transports FROM credentials WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            data = dict(row)
            data["can_trade"] = bool(data["can_trade"])
            data["has_credential"] = cred is not None
            if cred is not None:
                data["credential_id_hex"] = bytes(cred["credential_id"]).hex()
                data["sign_count"] = cred["sign_count"]
            return data

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT id FROM sessions ORDER BY created_at DESC").fetchall()
            return [self.get_session(r["id"]) for r in rows if r["id"]]  # type: ignore[misc]

    def update_touch(
        self,
        session_id: str,
        ip: str | None = None,
        country: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        now = self._now()
        with self._lock:
            curr = self._conn.execute(
                "SELECT last_ip, last_country, user_agent FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if curr is None:
                return
            self._conn.execute(
                """
                UPDATE sessions
                SET last_seen_at = ?,
                    last_ip = ?,
                    last_country = ?,
                    user_agent = ?
                WHERE id = ?
                """,
                (
                    now,
                    ip if ip is not None else curr["last_ip"],
                    country if country is not None else curr["last_country"],
                    user_agent if user_agent is not None else curr["user_agent"],
                    session_id,
                ),
            )
            self._conn.commit()

    def approve_session(
        self,
        session_id: str,
        pair_code: str,
        ip: str = "127.0.0.1",
        country: str = "LOCAL",
    ) -> dict[str, Any]:
        """Approves a PENDING session on the laptop after verifying the 6-digit pair_code."""
        with self._lock:
            sess = self.get_session(session_id)
            if sess is None:
                raise KeyError("Session not found")
            if sess["state"] != "PENDING":
                raise ValueError(f"Session cannot be approved in state '{sess['state']}'")
            expected_code = (sess.get("pair_code") or "").strip()
            if not expected_code or not secrets.compare_digest(expected_code, pair_code.strip()):
                self._log_event_unlocked(
                    session_id=session_id,
                    event="approval_failed_code_mismatch",
                    ip=ip,
                    country=country,
                    detail="Invalid 6-digit pairing confirmation code",
                )
                self._conn.commit()
                raise PermissionError("Invalid 6-digit confirmation code")

            now = self._now()
            # Transition to ACTIVE if credential is already registered; otherwise set approved_at
            # so it immediately becomes ACTIVE when passkey registration completes.
            new_state: SessionState = "ACTIVE" if sess["has_credential"] else "PENDING"
            self._conn.execute(
                """
                UPDATE sessions
                SET approved_at = ?, state = ?
                WHERE id = ?
                """,
                (now, new_state, session_id),
            )
            self._log_event_unlocked(
                session_id=session_id,
                event="session_approved",
                ip=ip,
                country=country,
                detail=f"state={new_state} has_credential={sess['has_credential']}",
            )
            self._conn.commit()
            return self.get_session(session_id)  # type: ignore[return-value]

    def mark_relink_required_all(self, old_host: str, new_host: str) -> int:
        """Marks every non-revoked session as RELINK_REQUIRED when the tunnel URL changes (Section 8.1 & 9)."""
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE sessions
                SET state = 'RELINK_REQUIRED'
                WHERE state != 'REVOKED' AND tunnel_host != ?
                """,
                (new_host,),
            )
            count = cur.rowcount
            # Invalidate one-time challenges and step-up tokens for affected sessions
            self._conn.execute(
                """
                DELETE FROM challenges WHERE session_id IN (
                    SELECT id FROM sessions WHERE state = 'RELINK_REQUIRED'
                )
                """
            )
            self._conn.execute(
                """
                DELETE FROM stepup_tokens WHERE session_id IN (
                    SELECT id FROM sessions WHERE state = 'RELINK_REQUIRED'
                )
                """
            )
            self._log_event_unlocked(
                session_id=None,
                event="tunnel_url_changed",
                ip="127.0.0.1",
                country="LOCAL",
                detail=f"old_host={old_host} new_host={new_host} relink_count={count}",
            )
            self._conn.commit()
            return count

    def reconnect_session(
        self,
        session_id: str,
        new_tunnel_host: str,
        ip: str = "127.0.0.1",
        country: str = "LOCAL",
    ) -> dict[str, Any]:
        """Issues a new pairing state & 6-digit code for a RELINK_REQUIRED session (Section 7)."""
        with self._lock:
            sess = self.get_session(session_id)
            if sess is None:
                raise KeyError("Session not found")
            if sess["state"] == "REVOKED":
                raise ValueError("Cannot reconnect a REVOKED session")

            pair_code = f"{secrets.randbelow(1_000_000):06d}"
            # Wipe old credential, cookies, challenges, and stepup tokens bound to the old hostname
            self._conn.execute("DELETE FROM credentials WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM cookies WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM challenges WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM stepup_tokens WHERE session_id = ?", (session_id,))
            self._conn.execute(
                """
                UPDATE sessions
                SET state = 'PENDING',
                    tunnel_host = ?,
                    pair_code = ?,
                    approved_at = NULL
                WHERE id = ?
                """,
                (new_tunnel_host, pair_code, session_id),
            )
            self._log_event_unlocked(
                session_id=session_id,
                event="session_reconnect_issued",
                ip=ip,
                country=country,
                detail=f"new_tunnel_host={new_tunnel_host}",
            )
            self._conn.commit()
            return self.get_session(session_id)  # type: ignore[return-value]

    def revoke_session(
        self,
        session_id: str,
        reason: str = "admin_delete",
        ip: str = "127.0.0.1",
        country: str = "LOCAL",
    ) -> dict[str, Any]:
        """Terminal revocation: sets state = REVOKED and wipes credentials, cookies, challenges, and step-up tokens."""
        with self._lock:
            sess = self.get_session(session_id)
            if sess is None:
                raise KeyError("Session not found")
            self._conn.execute("DELETE FROM credentials WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM cookies WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM challenges WHERE session_id = ?", (session_id,))
            self._conn.execute("DELETE FROM stepup_tokens WHERE session_id = ?", (session_id,))
            self._conn.execute(
                """
                UPDATE sessions
                SET state = 'REVOKED', pair_code = NULL, can_trade = 0
                WHERE id = ?
                """,
                (session_id,),
            )
            self._log_event_unlocked(
                session_id=session_id,
                event="session_revoked",
                ip=ip,
                country=country,
                detail=f"reason={reason}",
            )
            self._conn.commit()
            return self.get_session(session_id)  # type: ignore[return-value]

    def killswitch_all(self, ip: str = "127.0.0.1", country: str = "LOCAL") -> int:
        """Section 5.11 & 7: Stops mobile trading, revokes all sessions, and wipes all credentials/cookies."""
        with self._lock:
            self._conn.execute("DELETE FROM credentials")
            self._conn.execute("DELETE FROM cookies")
            self._conn.execute("DELETE FROM challenges")
            self._conn.execute("DELETE FROM stepup_tokens")
            cur = self._conn.execute(
                """
                UPDATE sessions
                SET state = 'REVOKED', pair_code = NULL, can_trade = 0
                WHERE state != 'REVOKED'
                """
            )
            revoked_count = cur.rowcount
            self._log_event_unlocked(
                session_id=None,
                event="killswitch_activated",
                ip=ip,
                country=country,
                detail=f"revoked_sessions={revoked_count}",
            )
            self._conn.commit()
            return revoked_count

    # -------------------------------------------------------------------------
    # Credentials
    # -------------------------------------------------------------------------

    def store_credential(
        self,
        session_id: str,
        credential_id: bytes,
        qx: int,
        qy: int,
        sign_count: int,
        transports: list[str] | None = None,
        user_agent: str | None = None,
        ip: str = "127.0.0.1",
        country: str = "XX",
    ) -> dict[str, Any]:
        """Stores the registered WebAuthn passkey public key for a PENDING session."""
        with self._lock:
            sess = self.get_session(session_id)
            if sess is None:
                raise KeyError("Session not found")
            if sess["state"] != "PENDING":
                raise ValueError(f"Cannot register passkey when session state is '{sess['state']}'")
            if sess["has_credential"]:
                raise ValueError("Session already has a registered passkey credential")

            pub_key_blob = json.dumps({"qx": f"0x{qx:064x}", "qy": f"0x{qy:064x}"}).encode("utf-8")
            transports_str = json.dumps(transports or ["internal"])
            self._conn.execute(
                """
                INSERT INTO credentials (session_id, credential_id, public_key, sign_count, transports)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, credential_id, pub_key_blob, sign_count, transports_str),
            )
            # If laptop already approved the pairing code, transition immediately to ACTIVE
            new_state: SessionState = "ACTIVE" if sess.get("approved_at") is not None else "PENDING"
            now = self._now()
            self._conn.execute(
                """
                UPDATE sessions
                SET state = ?, last_seen_at = ?, last_ip = ?, last_country = ?, user_agent = COALESCE(?, user_agent)
                WHERE id = ?
                """,
                (new_state, now, ip, country, user_agent, session_id),
            )
            self._log_event_unlocked(
                session_id=session_id,
                event="passkey_registered",
                ip=ip,
                country=country,
                detail=f"sign_count={sign_count} state={new_state}",
            )
            self._conn.commit()
            return self.get_session(session_id)  # type: ignore[return-value]

    def get_credential(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT session_id, credential_id, public_key, sign_count, transports FROM credentials WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            pk = json.loads(bytes(row["public_key"]).decode("utf-8"))
            return {
                "session_id": row["session_id"],
                "credential_id": bytes(row["credential_id"]),
                "qx": int(pk["qx"], 16),
                "qy": int(pk["qy"], 16),
                "sign_count": int(row["sign_count"]),
                "transports": json.loads(row["transports"] or '["internal"]'),
            }

    def update_sign_count(self, session_id: str, new_sign_count: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE credentials SET sign_count = ? WHERE session_id = ?",
                (new_sign_count, session_id),
            )
            self._conn.commit()

    # -------------------------------------------------------------------------
    # Cookies (256-bit random values, stored SHA-256 hashed in SQLite)
    # -------------------------------------------------------------------------

    def issue_cookie(self, session_id: str) -> str:
        """Generates a 256-bit random session cookie and stores only its SHA-256 hash on the server."""
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).digest()
        now = self._now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO cookies (token_hash, session_id, created_at) VALUES (?, ?, ?)",
                (token_hash, session_id, now),
            )
            self._conn.commit()
        return raw_token

    def resolve_cookie(self, raw_token: str | None) -> dict[str, Any] | None:
        """Looks up a session from its raw cookie value, ensuring the credential still exists (Section 5.4)."""
        if not raw_token:
            return None
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).digest()
        with self._lock:
            row = self._conn.execute(
                "SELECT session_id FROM cookies WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            sess = self.get_session(row["session_id"])
            if sess is None or not sess.get("has_credential"):
                return None
            return sess

    # -------------------------------------------------------------------------
    # One-time WebAuthn Challenges (~2 minute TTL)
    # -------------------------------------------------------------------------

    def create_challenge(
        self,
        session_id: str,
        purpose: ChallengePurpose,
        challenge_bytes: bytes | None = None,
        action_hash: bytes | None = None,
        ttl_seconds: int = CHALLENGE_TTL_SECONDS,
    ) -> tuple[str, bytes]:
        challenge_id = secrets.token_hex(16)
        challenge = challenge_bytes if challenge_bytes is not None else secrets.token_bytes(32)
        expires_at = self._now() + ttl_seconds
        with self._lock:
            # Prune expired challenges
            self._conn.execute("DELETE FROM challenges WHERE expires_at < ?", (self._now(),))
            self._conn.execute(
                """
                INSERT INTO challenges (id, session_id, purpose, challenge, action_hash, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (challenge_id, session_id, purpose, challenge, action_hash, expires_at),
            )
            self._conn.commit()
        return challenge_id, challenge

    def consume_challenge(
        self,
        session_id: str,
        purpose: ChallengePurpose,
        challenge_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Atomically fetches and deletes a single-use challenge if it exists and has not expired."""
        now = self._now()
        with self._lock:
            self._conn.execute("DELETE FROM challenges WHERE expires_at < ?", (now,))
            if challenge_id:
                row = self._conn.execute(
                    """
                    SELECT id, session_id, purpose, challenge, action_hash, expires_at
                    FROM challenges
                    WHERE id = ? AND session_id = ? AND purpose = ?
                    """,
                    (challenge_id, session_id, purpose),
                ).fetchone()
            else:
                row = self._conn.execute(
                    """
                    SELECT id, session_id, purpose, challenge, action_hash, expires_at
                    FROM challenges
                    WHERE session_id = ? AND purpose = ?
                    ORDER BY expires_at DESC LIMIT 1
                    """,
                    (session_id, purpose),
                ).fetchone()
            if row is None:
                return None
            self._conn.execute("DELETE FROM challenges WHERE id = ?", (row["id"],))
            self._conn.commit()
            return {
                "id": row["id"],
                "session_id": row["session_id"],
                "purpose": row["purpose"],
                "challenge": bytes(row["challenge"]),
                "action_hash": bytes(row["action_hash"]) if row["action_hash"] is not None else None,
                "expires_at": int(row["expires_at"]),
            }

    # -------------------------------------------------------------------------
    # Single-Use 60-Second Step-Up Tokens (Section 5.5 & Section 8.2)
    # -------------------------------------------------------------------------

    def issue_stepup_token(
        self,
        session_id: str,
        action_hash: bytes,
        ttl_seconds: int = STEPUP_TOKEN_TTL_SECONDS,
    ) -> str:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).digest()
        expires_at = self._now() + ttl_seconds
        with self._lock:
            self._conn.execute("DELETE FROM stepup_tokens WHERE expires_at < ?", (self._now(),))
            self._conn.execute(
                """
                INSERT INTO stepup_tokens (token_hash, session_id, action_hash, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (token_hash, session_id, action_hash, expires_at),
            )
            self._conn.commit()
        return raw_token

    def consume_stepup_token(
        self,
        session_id: str,
        raw_token: str | None,
        expected_action_hash: bytes,
    ) -> bool:
        """Atomically verifies and consumes a single-use 60-second step-up token bound to `expected_action_hash`."""
        if not raw_token:
            return False
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).digest()
        now = self._now()
        with self._lock:
            self._conn.execute("DELETE FROM stepup_tokens WHERE expires_at < ?", (now,))
            row = self._conn.execute(
                """
                SELECT session_id, action_hash, expires_at
                FROM stepup_tokens
                WHERE token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return False
            # Always delete on lookup so a token can never be replayed
            self._conn.execute("DELETE FROM stepup_tokens WHERE token_hash = ?", (token_hash,))
            self._conn.commit()
            if row["session_id"] != session_id:
                return False
            if int(row["expires_at"]) < now:
                return False
            stored_hash = bytes(row["action_hash"])
            return secrets.compare_digest(stored_hash, expected_action_hash)

    # -------------------------------------------------------------------------
    # Audit Log (Section 5.10 & Section 6)
    # -------------------------------------------------------------------------

    def log_event(
        self,
        session_id: str | None,
        event: str,
        ip: str = "127.0.0.1",
        country: str = "XX",
        detail: str = "",
    ) -> None:
        with self._lock:
            self._log_event_unlocked(session_id, event, ip, country, detail)
            self._conn.commit()

    def _log_event_unlocked(
        self,
        session_id: str | None,
        event: str,
        ip: str,
        country: str,
        detail: str,
    ) -> None:
        self._conn.execute(
            "INSERT INTO audit_log (ts, session_id, event, ip, country, detail) VALUES (?, ?, ?, ?, ?, ?)",
            (self._now(), session_id, event, ip, country, detail),
        )

    def list_audit_log(self, limit: int = 200, session_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if session_id:
                rows = self._conn.execute(
                    "SELECT ts, session_id, event, ip, country, detail FROM audit_log WHERE session_id = ? ORDER BY ts DESC, rowid DESC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT ts, session_id, event, ip, country, detail FROM audit_log ORDER BY ts DESC, rowid DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

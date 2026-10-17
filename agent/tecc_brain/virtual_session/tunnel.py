"""Cloudflare Quick-Tunnel Manager for Virtual Sessions (Section 8.1).

Spawns `cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8001` to expose ONLY
the Mobile Gateway port (8001), never the Admin App port (8000).
Defaults to the configured temporary URL `https://xxxx.trycloudflare.co` until a live
`cloudflared` process or custom domain is connected.
"""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from urllib.parse import urlparse

DEFAULT_TEMP_TUNNEL_URL = "https://xxxx.trycloudflare.co"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.(?:com|co)")


def extract_hostname(url_or_host: str) -> str:
    """Extracts the clean lowercase hostname (RP_ID) from a tunnel URL or hostname string."""
    raw = url_or_host.strip()
    if "://" in raw:
        parsed = urlparse(raw)
        return (parsed.hostname or raw).lower()
    return raw.split("/")[0].split(":")[0].lower()


def set_windows_keep_awake(enabled: bool) -> bool:
    """Section 8.4: Optionally disable sleep while sessions are active (Windows SetThreadExecutionState)."""
    if sys.platform != "win32":
        return False
    try:
        es_continuous = 0x80000000
        es_system_required = 0x00000001
        flags = (es_continuous | es_system_required) if enabled else es_continuous
        kernel32 = getattr(ctypes, "windll", None)
        if kernel32 is not None and hasattr(kernel32, "kernel32"):
            res = kernel32.kernel32.SetThreadExecutionState(flags)
            return bool(res)
    except Exception:
        return False
    return False


class TunnelManager:
    """Manages the outbound `cloudflared` quick-tunnel subprocess and watches for URL changes."""

    def __init__(
        self,
        cloudflared_path: str = "cloudflared",
        port: int = 8001,
        default_url: str | None = None,
        spawn_binary: bool = False,
    ) -> None:
        self.path = cloudflared_path
        self.port = port
        self.default_url = (
            default_url
            or os.environ.get("TECC_TUNNEL_URL")
            or os.environ.get("RP_ID")
            or DEFAULT_TEMP_TUNNEL_URL
        )
        if not self.default_url.startswith("http"):
            self.default_url = f"https://{self.default_url}"
        self.spawn_binary = spawn_binary or (os.environ.get("TECC_SPAWN_CLOUDFLARED", "0") == "1")
        self.proc: subprocess.Popen[str] | None = None
        self.url: str | None = None
        self.on_url_change: Callable[[str, str], None] | None = None
        self._lock = threading.Lock()
        self._watchdog_enabled = False

    @property
    def tunnel_host(self) -> str:
        """Returns the active tunnel hostname (used as WebAuthn rpID)."""
        active_url = self.url or self.default_url
        return extract_hostname(active_url)

    def start(self, timeout: float = 30.0) -> str:
        """Ensures the tunnel is running and returns its public HTTPS URL.

        If `spawn_binary` is enabled and `cloudflared` is installed, starts the subprocess
        and parses the assigned `https://*.trycloudflare.com` / `.co` URL. Otherwise uses
        the configured temporary URL (`https://xxxx.trycloudflare.co`).
        """
        with self._lock:
            if self.proc and self.proc.poll() is None and self.url:
                return self.url

            old = self.url
            if self.spawn_binary and shutil.which(self.path):
                self.proc = subprocess.Popen(
                    [
                        self.path,
                        "tunnel",
                        "--no-autoupdate",
                        "--url",
                        f"http://127.0.0.1:{self.port}",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                self.url = None
                t0 = time.time()
                assert self.proc.stdout is not None
                for line in self.proc.stdout:
                    m = URL_RE.search(line)
                    if m:
                        self.url = m.group(0)
                        break
                    if time.time() - t0 > timeout:
                        self.stop()
                        raise TimeoutError("cloudflared did not return a URL")
                if not self.url:
                    self.stop()
                    raise TimeoutError("cloudflared exited before returning a URL")
                self._watchdog_enabled = True
                threading.Thread(target=self._drain_and_watch, daemon=True).start()
            else:
                if self. url is None:
                    self.url = self.default_url

            new_url = self.url
            set_windows_keep_awake(True)

        if old and new_url and old != new_url and self.on_url_change:
            self.on_url_change(old, new_url)
        assert new_url is not None
        return new_url

    def _drain_and_watch(self) -> None:
        """Drains stdout pipe so cloudflared doesn't block; restarts on unexpected crash."""
        proc = self.proc
        if not proc or not proc.stdout:
            return
        try:
            for _ in proc.stdout:
                pass
        except Exception:
            pass
        # Process exited; if watchdog is still enabled, restart and trigger on_url_change
        if self._watchdog_enabled:
            try:
                self.start()
            except Exception:
                pass

    def simulate_url_change(self, new_url: str) -> str:
        """Simulates a cloudflared crash/restart or laptop wake that assigns a new random quick-tunnel URL.

        Triggers `on_url_change(old_url, new_url)` which transitions all non-revoked sessions
        to `RELINK_REQUIRED`.
        """
        normalized = new_url.strip()
        if not normalized.startswith("http"):
            normalized = f"https://{normalized}"
        with self._lock:
            old = self.url or self.default_url
            self.url = normalized
            self.default_url = normalized
        if old != normalized and self.on_url_change:
            self.on_url_change(old, normalized)
        return normalized

    def stop(self) -> None:
        """Stops the tunnel process and clears the active URL (used by Kill Switch and shutdown)."""
        with self._lock:
            self._watchdog_enabled = False
            if self.proc:
                try:
                    self.proc.terminate()
                except Exception:
                    pass
                self.proc = None
            self.url = None
            set_windows_keep_awake(False)

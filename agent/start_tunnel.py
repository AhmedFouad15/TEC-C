"""Cloudflare Tunnel Runner for Tec-C Command Center.

Exposes the local Brain backend (http://127.0.0.1:8000) over a secure HTTPS Cloudflare Tunnel,
allowing https://www.tec-c.xyz to connect directly to your local backend with zero mixed-content issues.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.(?:com|co)")


def find_cloudflared() -> str | None:
    foundry_bin = Path(os.environ.get("USERPROFILE", "")) / ".foundry" / "bin" / "cloudflared.exe"
    if foundry_bin.exists():
        return str(foundry_bin)
    for name in ("cloudflared", "cloudflared.exe"):
        which = shutil.which(name)
        if which:
            return which
    return None


def main() -> None:
    bin_path = find_cloudflared()
    if not bin_path:
        print("[!] cloudflared binary not found in PATH or ~/.foundry/bin/")
        sys.exit(1)

    print(f"[*] Starting Cloudflare Tunnel pointing to http://127.0.0.1:8000 ...")
    proc = subprocess.Popen(
        [bin_path, "tunnel", "--url", "http://127.0.0.1:8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    tunnel_url = None
    t0 = time.time()
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            m = URL_RE.search(line)
            if m:
                tunnel_url = m.group(0)
                break
            if time.time() - t0 > 30:
                break
    except KeyboardInterrupt:
        proc.terminate()
        return

    if tunnel_url:
        print("\n" + "=" * 70)
        print("  TEC-C COMMAND CENTER SECURE TUNNEL ACTIVE")
        print("=" * 70)
        print(f"  Backend HTTPS URL: {tunnel_url}")
        print(f"  Live App Direct URL:\n  https://www.tec-c.xyz/app.html?api={tunnel_url}")
        print("=" * 70 + "\n")
        print("[*] Tunnel is running. Press Ctrl+C to stop.")

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("\n[*] Stopping tunnel...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()

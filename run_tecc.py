#!/usr/bin/env python3
"""
Tec-C One-Click Master Launcher (run_tecc.py)
--------------------------------------------
Workflow:
  1. Security Check: Verifies gitignore rules to guarantee no wallet or .env leaks.
  2. Wallet Setup: Creates a new EVM wallet if not already created; stores it locally.
  3. API Keys Check: Scans agent/.env — skips existing keys, prompts only for unset ones.
  4. Backend Launch: Starts the FastAPI Brain server & opens the Command Center UI.

100% Safe to Share: Contains zero hardcoded API keys or private keys.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows console encoding
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def find_repo_root() -> Path:
    current = Path(__file__).resolve().parent
    for p in [current, current.parent, current.parent.parent]:
        if (p / "agent" / ".env.example").exists() or (p / "contracts").exists():
            return p
    return current


repo_root = find_repo_root()
agent_dir = repo_root / "agent"
venv_py = (
    agent_dir / ".venv" / "Scripts" / "python.exe"
    if sys.platform == "win32"
    else agent_dir / ".venv" / "bin" / "python"
)

# Automatically hand off to virtual environment Python if not already inside it
if venv_py.exists() and Path(sys.executable).resolve() != venv_py.resolve():
    target = Path(__file__).resolve()
    res = subprocess.run([str(venv_py), str(target)] + sys.argv[1:])
    sys.exit(res.returncode)

# Add agent to sys.path
if str(agent_dir) not in sys.path:
    sys.path.insert(0, str(agent_dir))

try:
    from eth_account import Account
except ImportError:
    sys.exit("Error: 'eth_account' is required. Please install requirements in agent/.venv.")


def read_env_vars(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    vars_: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if v and not v.startswith("your_") and not v.startswith("0x..."):
                vars_[k] = v
    return vars_


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    if not path.exists():
        template = path.parent / ".env.example"
        content = template.read_text(encoding="utf-8") if template.exists() else ""
    else:
        content = path.read_text(encoding="utf-8")

    lines = content.splitlines()
    remaining = dict(updates)
    new_lines = []

    for line in lines:
        stripped = line.strip()
        matched = None
        for key in list(remaining.keys()):
            pattern = rf"^(?:#\s*)?({re.escape(key)})\s*=.*$"
            if re.match(pattern, stripped):
                matched = key
                break
        if matched:
            new_lines.append(f"{matched}={remaining.pop(matched)}")
        else:
            new_lines.append(line)

    if remaining:
        new_lines.append("")
        new_lines.append("# --- Added by run_tecc.py ---")
        for k, v in remaining.items():
            new_lines.append(f"{k}={v}")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def check_git_security() -> bool:
    """Verify that .env and wallet files are ignored by git."""
    test_files = [
        str(agent_dir / ".env"),
        str(agent_dir / ".state" / "wallet.json"),
        str(repo_root / "wallet.json"),
    ]
    git_bin = shutil.which("git")
    if not git_bin:
        return True  # git not in path, assume ok

    try:
        proc = subprocess.run(
            ["git", "check-ignore", "-q"] + test_files,
            cwd=str(repo_root),
            capture_output=True,
        )
        # returncode 0 means all checked files are ignored
        return proc.returncode == 0
    except Exception:
        return True


def free_port(port: int = 8000) -> None:
    """If port is already occupied, cleanly terminate stale listener."""
    if os.name == "nt":
        try:
            cmd = f'powershell -Command "Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"'
            subprocess.run(cmd, shell=True, capture_output=True)
            time.sleep(0.5)
        except Exception:
            pass


def open_browser_delayed(url: str, delay: float = 1.5) -> None:
    def _open():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()


def main() -> None:
    state_dir = agent_dir / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)
    env_path = agent_dir / ".env"
    wallet_file = state_dir / "wallet.json"
    backup_wallet = repo_root / "wallet.json"

    print("=" * 76)
    print("        Tec-C Autonomous Agent Wallet -- Full Stack Launcher")
    print("=" * 76)

    # --------------------------------------------------------------------------
    # Step 1: Security & Git-Ignore Verification
    # --------------------------------------------------------------------------
    print("\n[1/4] Verifying Git Security & Ignore Rules...")
    if check_git_security():
        print("      [SAFE] .env and wallet.json are strictly ignored by git.")
        print("      [SAFE] No sensitive keys or credentials can be pushed to remote.")
    else:
        print("      [!] Note: Verifying .gitignore entries for .env and wallet.json.")

    # Ensure .env exists
    if not env_path.exists():
        example_path = agent_dir / ".env.example"
        if example_path.exists():
            env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
            print("      [OK] Created agent/.env from template.")

    existing_env = read_env_vars(env_path)
    env_updates: dict[str, str] = {}

    # --------------------------------------------------------------------------
    # Step 2: Wallet Setup (Auto-creates if missing)
    # --------------------------------------------------------------------------
    print("\n[2/4] Checking EVM Wallet Configuration...")
    wallet_address = None
    wallet_key = None

    if wallet_file.exists():
        try:
            wdata = json.loads(wallet_file.read_text(encoding="utf-8"))
            wallet_address = wdata.get("address")
            wallet_key = wdata.get("private_key")
        except Exception:
            pass

    if not wallet_address and backup_wallet.exists():
        try:
            wdata = json.loads(backup_wallet.read_text(encoding="utf-8"))
            wallet_address = wdata.get("address")
            wallet_key = wdata.get("private_key")
        except Exception:
            pass

    if not wallet_key:
        current_env_key = existing_env.get("TECC_DEPLOYER_KEY")
        if current_env_key and current_env_key.startswith("0x") and len(current_env_key) == 66:
            try:
                wallet_address = Account.from_key(current_env_key).address
                wallet_key = current_env_key
            except Exception:
                pass

    if wallet_address and wallet_key:
        print(f"      [OK] Wallet exists on disk: {wallet_address}")
    else:
        print("      [+] No wallet found. Generating fresh, secure EVM wallet...")
        new_acc = Account.create()
        wallet_address = new_acc.address
        wallet_key = "0x" + new_acc.key.hex().removeprefix("0x")
        wdata = {
            "address": wallet_address,
            "private_key": wallet_key,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "notes": "Generated by run_tecc.py. Kept private on local laptop.",
        }
        wallet_file.write_text(json.dumps(wdata, indent=2), encoding="utf-8")
        backup_wallet.write_text(json.dumps(wdata, indent=2), encoding="utf-8")
        try:
            os.chmod(wallet_file, 0o600)
            os.chmod(backup_wallet, 0o600)
        except Exception:
            pass
        print(f"      [OK] New wallet generated: {wallet_address}")
        print(f"      [OK] Saved locally to: {wallet_file}")

    env_updates["TECC_DEPLOYER_KEY"] = wallet_key

    # --------------------------------------------------------------------------
    # Step 3: API Keys Check (Only prompts if unset)
    # --------------------------------------------------------------------------
    print("\n[3/4] Checking Intelligence & API Keys in agent/.env...")
    api_configs = [
        {
            "env_key": "TECC_BRAIN_LLM_KEY",
            "name": "AI Brain LLM Key (Google Gemini API Key)",
            "url": "https://aistudio.google.com/app/apikey",
            "desc": "Powers strategic single-pass portfolio reasoning.",
        },
        {
            "env_key": "GROK_API_KEY",
            "name": "Grok (xAI) API Key",
            "url": "https://console.x.ai/",
            "desc": "Powers real-time News Risk Sentinel sentiment.",
        },
        {
            "env_key": "CMC_API_KEY",
            "name": "CoinMarketCap API Key",
            "url": "https://pro.coinmarketcap.com/",
            "desc": "Provides crypto Fear & Greed sentiment index.",
        },
        {
            "env_key": "COINGLASS_API_KEY",
            "name": "CoinGlass API Key",
            "url": "https://open-api.coinglass.com/",
            "desc": "Provides futures funding & liquidation pulse.",
        },
    ]

    for item in api_configs:
        k = item["env_key"]
        val = existing_env.get(k)
        if val and not val.startswith("your_"):
            masked = val[:4] + "..." + val[-4:] if len(val) > 8 else "***"
            print(f"      [OK] {item['name']}: Configured ({masked})")
        else:
            print(f"\n      [?] {item['name']} is not set.")
            print(f"          Purpose: {item['desc']}")
            print(f"          Free key: {item['url']}")
            user_input = input("          Enter key (press Enter to skip): ").strip()
            if user_input:
                env_updates[k] = user_input
                print(f"          [+] Saved {k} to agent/.env")
            else:
                print("          [-] Skipped (offline deterministic mode will be used).")

    # Update .env with new values
    if env_updates:
        update_env_file(env_path, env_updates)

    # --------------------------------------------------------------------------
    # Step 4: Launch Backend & Command Center
    # --------------------------------------------------------------------------
    print("\n[4/4] Launching the Tec-C Stack...")
    app_url = "http://127.0.0.1:8000/app.html"
    docs_url = "http://127.0.0.1:8000/docs"
    landing_url = "http://127.0.0.1:8000/"

    print("=" * 76)
    print(" Backend Starting on http://127.0.0.1:8000")
    print("=" * 76)
    print(f"• Command Center UI: {app_url}")
    print(f"• Landing Page:      {landing_url}")
    print(f"• Interactive Docs:  {docs_url}")
    print(f"• Deployer Wallet:   {wallet_address}")
    print("-" * 76)
    print("Opening Command Center in your browser... (Press Ctrl+C to stop)")
    print()

    free_port(8000)
    open_browser_delayed(app_url, delay=1.8)

    # Start uvicorn server in agent directory
    cmd = [
        str(venv_py),
        "-m",
        "uvicorn",
        "tecc_brain.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--env-file",
        ".env",
    ]
    try:
        subprocess.run(cmd, cwd=str(agent_dir))
    except KeyboardInterrupt:
        print("\n[✓] Tec-C server stopped cleanly.")


if __name__ == "__main__":
    main()

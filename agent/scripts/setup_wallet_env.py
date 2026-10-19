#!/usr/bin/env python3
"""
Tec-C Automated Wallet Setup & Environment Configuration Wizard
--------------------------------------------------------------
Features:
  1. Automatically generates a fresh EVM wallet (or loads an existing one).
  2. Stores wallet keys securely in a git-ignored local file on your laptop.
  3. Updates `agent/.env` with the wallet private key (TECC_DEPLOYER_KEY).
  4. Intelligently scans `agent/.env` for API keys (Gemini, Grok, CMC, CoinGlass):
     - If an API key is already configured, it is skipped and preserved.
     - If an API key is unset or commented out, it prompts you to enter it.
  5. 100% SAFE TO SHARE: Contains zero hardcoded private keys or API keys.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Fix Windows console encoding if needed
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def find_repo_root() -> Path:
    """Find the root repository directory."""
    current = Path(__file__).resolve().parent
    for p in [current, current.parent, current.parent.parent]:
        if (p / "agent" / ".env.example").exists() or (p / "contracts").exists():
            return p
    return current


# Re-execute with venv if eth_account is not installed in the current environment
try:
    from eth_account import Account
except ImportError:
    repo_root = find_repo_root()
    venv_py = (
        repo_root / "agent" / ".venv" / "Scripts" / "python.exe"
        if sys.platform == "win32"
        else repo_root / "agent" / ".venv" / "bin" / "python"
    )
    if venv_py.exists():
        target = Path(__file__).resolve()
        res = subprocess.run([str(venv_py), str(target)] + sys.argv[1:])
        sys.exit(res.returncode)
    else:
        sys.exit(
            "Error: 'eth_account' is required. Please activate the virtual environment:\n"
            "  cd agent && .venv\\Scripts\\activate (Windows)\n"
            "or run with: agent/.venv/bin/python setup_wallet_env.py"
        )


def read_env_file(path: Path) -> dict[str, str]:
    """Parse active non-commented key=value pairs from a .env file."""
    if not path.exists():
        return {}
    env_vars: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if v and not v.startswith("your_") and not v.startswith("0x..."):
                env_vars[k] = v
    return env_vars


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    """Safely update or uncomment keys in the .env file while preserving layout."""
    if not path.exists():
        template = path.parent / ".env.example"
        if template.exists():
            content = template.read_text(encoding="utf-8")
        else:
            content = ""
    else:
        content = path.read_text(encoding="utf-8")

    lines = content.splitlines()
    remaining = dict(updates)

    new_lines = []
    for line in lines:
        stripped = line.strip()
        matched_key = None
        for key in list(remaining.keys()):
            # Matches: KEY=value or # KEY=value or # KEY=
            pattern = rf"^(?:#\s*)?({re.escape(key)})\s*=.*$"
            if re.match(pattern, stripped):
                matched_key = key
                break

        if matched_key:
            new_lines.append(f"{matched_key}={remaining.pop(matched_key)}")
        else:
            new_lines.append(line)

    # Append any remaining keys not found in file
    if remaining:
        new_lines.append("")
        new_lines.append("# --- Added by setup_wallet_env.py ---")
        for k, v in remaining.items():
            new_lines.append(f"{k}={v}")

    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def main() -> None:
    repo_root = find_repo_root()
    agent_dir = repo_root / "agent"
    state_dir = agent_dir / ".state"
    state_dir.mkdir(parents=True, exist_ok=True)

    env_path = agent_dir / ".env"
    wallet_file = state_dir / "wallet.json"
    backup_wallet_file = repo_root / "wallet.json"

    print("=" * 72)
    print(" Tec-C Autonomous Agent Wallet -- Automated Setup & Onboarding Wizard")
    print("=" * 72)
    print(f"Repository Root: {repo_root}")
    print(f"Target .env:     {env_path}")
    print()

    # Ensure .env exists
    if not env_path.exists():
        example_path = agent_dir / ".env.example"
        if example_path.exists():
            env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
            print("[OK] Created agent/.env from agent/.env.example template.")

    existing_env = read_env_file(env_path)
    env_updates: dict[str, str] = {}

    # --------------------------------------------------------------------------
    # 1. Wallet Setup
    # --------------------------------------------------------------------------
    print("--- [1/3] EVM Wallet Configuration ---")
    current_key = existing_env.get("TECC_DEPLOYER_KEY")
    wallet_data: dict[str, str] = {}

    if wallet_file.exists():
        try:
            wallet_data = json.loads(wallet_file.read_text(encoding="utf-8"))
        except Exception:
            wallet_data = {}

    if wallet_data.get("address") and wallet_data.get("private_key"):
        addr = wallet_data["address"]
        print(f"[i] Found existing local wallet on disk: {addr}")
        choice = input("    Do you want to keep using this wallet? [Y/n]: ").strip().lower()
        if choice in ("", "y", "yes"):
            use_existing = True
        else:
            use_existing = False
    elif current_key and current_key.startswith("0x") and len(current_key) == 66:
        try:
            recovered = Account.from_key(current_key)
            print(f"[i] Found existing key in .env: {recovered.address}")
            choice = input("    Do you want to keep using this wallet? [Y/n]: ").strip().lower()
            use_existing = choice in ("", "y", "yes")
            if use_existing:
                wallet_data = {
                    "address": recovered.address,
                    "private_key": current_key,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
        except Exception:
            use_existing = False
    else:
        use_existing = False

    if not use_existing:
        print("[+] Generating fresh, cryptographically secure EVM wallet...")
        new_account = Account.create()
        private_key_hex = "0x" + new_account.key.hex().removeprefix("0x")
        wallet_data = {
            "address": new_account.address,
            "private_key": private_key_hex,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "notes": (
                "Created by setup_wallet_env.py. Use for testnets only. "
                "Keep this file private and never commit it to git."
            ),
        }
        # Write to state_dir and repo backup (both git-ignored)
        wallet_file.write_text(json.dumps(wallet_data, indent=2), encoding="utf-8")
        backup_wallet_file.write_text(json.dumps(wallet_data, indent=2), encoding="utf-8")
        try:
            os.chmod(wallet_file, 0o600)
            os.chmod(backup_wallet_file, 0o600)
        except Exception:
            pass
        print(f"[OK] New wallet successfully created!")
        print(f"    Public Address: {wallet_data['address']}")
        print(f"    Saved securely: {wallet_file} (and backup at {backup_wallet_file})")

    env_updates["TECC_DEPLOYER_KEY"] = wallet_data["private_key"]
    wallet_address = wallet_data["address"]

    # --------------------------------------------------------------------------
    # 2. Network Selection
    # --------------------------------------------------------------------------
    print("\n--- [2/3] Target Testnet Network ---")
    current_network = existing_env.get("TECC_NETWORK", "arbitrum")
    print("Select the blockchain network you want to deploy to:")
    print("  1) Arbitrum Sepolia (Recommended: fast L2 execution for commodities/vault)")
    print("  2) Ethereum Sepolia (L1 testnet)")
    print("  3) Local Anvil (Local offline development)")
    print("  4) Consortium Node (Zero-gas testnet)")
    net_choice = input(f"Enter choice [1-4, press Enter for current '{current_network}']: ").strip()

    network_map = {"1": "arbitrum", "2": "sepolia", "3": "anvil", "4": "fisco_bcos"}
    selected_network = network_map.get(net_choice, current_network)
    env_updates["TECC_NETWORK"] = selected_network
    print(f"[OK] Active network set to: {selected_network}")

    if selected_network == "arbitrum":
        env_updates.setdefault(
            "ARBITRUM_RPC_URL",
            existing_env.get("ARBITRUM_RPC_URL", "https://sepolia-rollup.arbitrum.io/rpc"),
        )
    elif selected_network == "sepolia":
        env_updates.setdefault(
            "SEPOLIA_RPC_URL",
            existing_env.get("SEPOLIA_RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com"),
        )

    # --------------------------------------------------------------------------
    # 3. API Keys Configuration (Only asks if unset)
    # --------------------------------------------------------------------------
    print("\n--- [3/3] Intelligence & API Keys ---")

    api_keys = [
        {
            "env_key": "TECC_BRAIN_LLM_KEY",
            "name": "AI Brain LLM Key (Google Gemini API Key)",
            "url": "https://aistudio.google.com/app/apikey",
            "required": False,
            "desc": "Powers real-time single-pass strategic portfolio reasoning.",
        },
        {
            "env_key": "GROK_API_KEY",
            "name": "Grok (xAI) API Key",
            "url": "https://console.x.ai/",
            "required": False,
            "desc": "Powers News Risk Sentinel real-time breaking market analysis.",
        },
        {
            "env_key": "CMC_API_KEY",
            "name": "CoinMarketCap API Key",
            "url": "https://pro.coinmarketcap.com/",
            "required": False,
            "desc": "Provides real-time crypto Fear & Greed sentiment index.",
        },
        {
            "env_key": "COINGLASS_API_KEY",
            "name": "CoinGlass API Key",
            "url": "https://open-api.coinglass.com/",
            "required": False,
            "desc": "Provides futures funding rates and liquidation pulse data.",
        },
    ]

    for item in api_keys:
        k = item["env_key"]
        val = existing_env.get(k)
        if val and not val.startswith("your_"):
            masked = val[:4] + "..." + val[-4:] if len(val) > 8 else "***"
            print(f"[OK] {item['name']}: Already configured ({masked})")
        else:
            print(f"\n[?] {item['name']} is currently not set.")
            print(f"    Purpose: {item['desc']}")
            print(f"    Get key: {item['url']}")
            user_val = input(f"    Enter key (press Enter to skip): ").strip()
            if user_val:
                env_updates[k] = user_val
                print(f"    [+] Saved {k} to .env")
            else:
                print(f"    [-] Skipped (deterministic fallback will be used).")

    # Save updates
    update_env_file(env_path, env_updates)
    print("\n" + "=" * 72)
    print(" Setup Complete! Environment and Wallet Ready")
    print("=" * 72)
    print(f"• Wallet Address: {wallet_address}")
    print(f"• Active Network: {selected_network}")
    print(f"• Config File:    {env_path}")
    print(f"• Key Backup:     {wallet_file}")

    print("\n[!] Next Step -- Fund your wallet with testnet tokens:")
    if selected_network == "arbitrum":
        print(f"    1. Open: https://faucets.chain.link or https://bridge.arbitrum.io")
        print(f"    2. Paste your address: {wallet_address}")
        print(f"    3. Request Arbitrum Sepolia ETH (0.002 - 0.005 ETH is plenty)")
        print(f"\n    Then deploy and go live with:")
        print(f"    cd agent && .venv\\Scripts\\python.exe scripts/deploy_market_chain.py --network arbitrum")
    elif selected_network == "sepolia":
        print(f"    1. Open: https://sepoliafaucet.com or https://faucets.chain.link")
        print(f"    2. Paste your address: {wallet_address}")
        print(f"    3. Request Sepolia ETH")
        print(f"\n    Then deploy and go live with:")
        print(f"    cd agent && .venv\\Scripts\\python.exe scripts/deploy_market_chain.py --network sepolia")
    else:
        print(f"    Run local stack: powershell -ExecutionPolicy Bypass -File .\\dev_up.ps1")

    print("\nDone! You're ready to deploy.\n")


if __name__ == "__main__":
    main()

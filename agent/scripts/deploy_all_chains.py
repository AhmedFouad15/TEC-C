#!/usr/bin/env python3
"""
Tec-C Multi-Chain Deployment Orchestrator
----------------------------------------
Deploys the Tec-C Vault Suite across ALL supported chains so the AI Brain
can execute autonomously across every market simultaneously:

  1. Arbitrum Sepolia   -> Commodities Market (PAXG Gold, Commodities LP)
  2. Ethereum Sepolia   -> Crypto Market (Lido Staking, Curve LP, Aave v3)
  3. FISCO BCOS Node    -> Onshore Market (Shibor Treasury MMF) - zero-gas
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
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
if str(agent_dir) not in sys.path:
    sys.path.insert(0, str(agent_dir))

venv_py = (
    agent_dir / ".venv" / "Scripts" / "python.exe"
    if sys.platform == "win32"
    else agent_dir / ".venv" / "bin" / "python"
)

# Only delegate to venv Python if not already executing inside it
if venv_py.exists() and Path(sys.executable).resolve() != venv_py.resolve():
    target = Path(__file__).resolve()
    res = subprocess.run([str(venv_py), str(target)] + sys.argv[1:])
    sys.exit(res.returncode)

try:
    from eth_account import Account
    from tecc_brain.onchain.rpc import Rpc
except ImportError as err:
    sys.exit(f"Error importing dependencies: {err}. Please ensure agent/.venv is installed.")


def load_env(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    vars_: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            vars_[k.strip()] = v.strip().strip("'\"")
    return vars_


def check_balance_eth(rpc: Rpc, address: str) -> float:
    try:
        bal_hex = rpc.call("eth_getBalance", [address, "latest"])
        return int(bal_hex, 16) / 10**18
    except Exception:
        return 0.0


def main() -> None:
    env_path = agent_dir / ".env"
    deploy_script = agent_dir / "scripts" / "deploy_market_chain.py"

    parser = argparse.ArgumentParser(description="Deploy Tec-C Vault across all chains")
    parser.add_argument("--smoke", action="store_true", help="Run verification smoke test on all deployed chains")
    parser.add_argument("--skip-fisco", action="store_true", help="Skip local FISCO BCOS node deployment")
    parser.add_argument("--skip-arbitrum", action="store_true", help="Skip Arbitrum deployment and use Ethereum Sepolia only")
    args = parser.parse_args()

    print("=" * 76)
    print(" Tec-C Autonomous Multi-Chain Deployment Orchestrator")
    print("=" * 76)

    env = load_env(env_path)
    deployer_key = env.get("TECC_DEPLOYER_KEY")

    if not deployer_key or deployer_key.startswith("0x...") or len(deployer_key) < 64:
        print("\n[!] Error: No valid TECC_DEPLOYER_KEY found in agent/.env.")
        print("    Please run the wallet setup wizard first:")
        print("    python agent/scripts/setup_wallet_env.py\n")
        sys.exit(1)

    deployer_account = Account.from_key(deployer_key)
    deployer_address = deployer_account.address
    print(f"Deployer / Root Owner: {deployer_address}")
    print(f"Active Environment:    {env_path}")
    print()

    # Define the 3 chains and their parameters
    chains = [
        {
            "id": "arbitrum",
            "name": "Arbitrum Sepolia",
            "market": "Commodities Market (PAXG Gold, Commodities LP)",
            "rpc": env.get("ARBITRUM_RPC_URL", "https://sepolia-rollup.arbitrum.io/rpc"),
            "min_eth": 0.001,
            "fund_session": 0.0005,
            "faucet": "https://faucets.chain.link or https://bridge.arbitrum.io",
            "smoke_venue": "paxg_hold",
        },
        {
            "id": "sepolia",
            "name": "Ethereum Sepolia",
            "market": "Crypto Market (Lido Staking, Curve LP, Aave v3)",
            "rpc": env.get("SEPOLIA_RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com"),
            "min_eth": 0.015,
            "fund_session": 0.002,
            "faucet": "https://sepoliafaucet.com or https://faucets.chain.link",
            "smoke_venue": "aave_v3_usdc",
        },
        {
            "id": "fisco_bcos",
            "name": "FISCO BCOS Node",
            "market": "Onshore Market (Shibor Treasury MMF)",
            "rpc": env.get("FISCO_BCOS_RPC_URL", "http://127.0.0.1:8555"),
            "min_eth": 0.0,
            "fund_session": 0.0,
            "no_native_coin": True,
            "faucet": "N/A (Zero-Gas Consortium Chain)",
            "smoke_venue": "shibor_mmf",
        },
    ]

    results: list[dict] = []

    for chain in chains:
        cid = chain["id"]
        cname = chain["name"]
        rpc_url = chain["rpc"]
        print("-" * 76)
        print(f"[*] Processing {cname} [{chain['market']}]")
        print(f"    RPC Endpoint: {rpc_url}")

        if cid == "arbitrum" and args.skip_arbitrum:
            print("    [-] Skipped (--skip-arbitrum flag passed).")
            results.append({"chain": cname, "status": "SKIPPED", "detail": "Flag --skip-arbitrum"})
            continue

        if cid == "fisco_bcos" and args.skip_fisco:
            print("    [-] Skipped (--skip-fisco flag passed).")
            results.append({"chain": cname, "status": "SKIPPED", "detail": "Flag --skip-fisco"})
            continue

        # Test RPC connectivity
        try:
            rpc = Rpc(rpc_url, timeout_s=8)
            chain_id = rpc.chain_id()
            print(f"    [OK] Node reachable (Chain ID: {chain_id})")
        except Exception as e:
            if cid == "fisco_bcos":
                print(f"    [-] FISCO BCOS node not reachable at {rpc_url}.")
                print(f"        (To enable onshore market live, start the FISCO BCOS node per MULTICHAIN_NODES.md)")
                results.append({"chain": cname, "status": "SIMULATED", "detail": "Node offline (simulated)"})
                continue
            else:
                print(f"    [!] Failed to reach RPC at {rpc_url}: {e}")
                results.append({"chain": cname, "status": "ERROR", "detail": "RPC unreachable"})
                continue

        # Check gas balance (for public EVM chains)
        balance = check_balance_eth(rpc, deployer_address)
        print(f"    Deployer Balance: {balance:.6f} ETH")

        if balance < chain["min_eth"] and not chain.get("no_native_coin"):
            print(f"    [!] Insufficient funds on {cname}: need at least {chain['min_eth']} ETH.")
            print(f"        Please request testnet ETH for: {deployer_address}")
            print(f"        Faucet: {chain['faucet']}")
            results.append({"chain": cname, "status": "NEEDS_GAS", "detail": f"Need {chain['min_eth']} ETH (has {balance:.4f})"})
            continue

        # Deploy
        print(f"    [+] Deploying vault contracts & provisioning session key...")
        cmd = [
            sys.executable,
            str(deploy_script),
            "--network", cid,
            "--rpc", rpc_url,
            "--fund-session-eth", str(chain["fund_session"]),
        ]
        if chain.get("no_native_coin"):
            cmd.append("--no-native-coin")

        os.environ["TECC_DEPLOYER_KEY"] = deployer_key
        sub = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(agent_dir))

        if sub.returncode == 0:
            print(f"    [OK] Deployment successful on {cname}!")
            tec_account = ""
            for line in sub.stdout.splitlines():
                if "TecAccount" in line:
                    tec_account = line.split()[-1]
                if "session key" in line:
                    print(f"        {line.strip()}")

            if args.smoke:
                print(f"    [+] Running on-chain smoke test on {cname}...")
                smoke_cmd = [
                    sys.executable,
                    str(deploy_script),
                    "--network", cid,
                    "--smoke", "25",
                    "--smoke-venue", chain["smoke_venue"],
                ]
                smoke_sub = subprocess.run(smoke_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(agent_dir))
                if smoke_sub.returncode == 0:
                    print(f"        [OK] Smoke test passed! Output:\n        " + "\n        ".join(smoke_sub.stdout.strip().splitlines()[-2:]))
                else:
                    print(f"        [!] Smoke test warning: {smoke_sub.stdout.strip()}")

            results.append({"chain": cname, "status": "LIVE", "detail": f"Vault: {tec_account[:10]}..."})
        else:
            print(f"    [!] Deployment failed on {cname}:")
            for err_line in sub.stdout.splitlines()[-4:]:
                print(f"        {err_line}")
            results.append({"chain": cname, "status": "FAILED", "detail": "Transaction reverted / failed"})

    print("\n" + "=" * 76)
    print(" Multi-Chain Deployment Summary")
    print("=" * 76)
    print(f"{'Network':<22} | {'Status':<12} | {'Details'}")
    print("-" * 76)
    for r in results:
        status_color = "[LIVE]" if r["status"] == "LIVE" else f"[{r['status']}]"
        print(f"{r['chain']:<22} | {status_color:<12} | {r['detail']}")
    print("-" * 76)

    live_count = sum(1 for r in results if r["status"] == "LIVE")
    print(f"\n[OK] {live_count} market(s) now LIVE for the AI Brain.")
    print("     Start the Brain API and Command Center:")
    print("     powershell -ExecutionPolicy Bypass -File .\\dev_up.ps1\n")


if __name__ == "__main__":
    main()

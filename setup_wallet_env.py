#!/usr/bin/env python3
"""Convenience root entrypoint for setup_wallet_env.py"""
import os
import sys
import subprocess
from pathlib import Path

repo_root = Path(__file__).resolve().parent
agent_dir = repo_root / "agent"
script_path = agent_dir / "scripts" / "setup_wallet_env.py"

venv_py = (
    agent_dir / ".venv" / "Scripts" / "python.exe"
    if sys.platform == "win32"
    else agent_dir / ".venv" / "bin" / "python"
)

# Check if eth_account can be imported in the current Python interpreter
try:
    import eth_account
except ImportError:
    # Delegate to the project virtual environment
    if venv_py.exists():
        res = subprocess.run([str(venv_py), str(script_path)] + sys.argv[1:])
        sys.exit(res.returncode)
    else:
        sys.exit(
            "Error: Virtual environment not found at agent/.venv.\n"
            "Please create it:\n"
            "  cd agent\n"
            "  python -m venv .venv\n"
            "  .venv\\Scripts\\pip install -r requirements.txt\n"
        )

# If eth_account is available in the current Python, run directly
sys.path.insert(0, str(script_path.parent))
import setup_wallet_env

if __name__ == "__main__":
    setup_wallet_env.main()

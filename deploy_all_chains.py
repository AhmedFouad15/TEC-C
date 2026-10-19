#!/usr/bin/env python3
"""Convenience root entrypoint for deploy_all_chains.py"""
import os
import sys
import subprocess
from pathlib import Path

repo_root = Path(__file__).resolve().parent
agent_dir = repo_root / "agent"
script_path = agent_dir / "scripts" / "deploy_all_chains.py"

venv_py = (
    agent_dir / ".venv" / "Scripts" / "python.exe"
    if sys.platform == "win32"
    else agent_dir / ".venv" / "bin" / "python"
)

# Hand off to project venv if running with system python
if venv_py.exists() and Path(sys.executable).resolve() != venv_py.resolve():
    res = subprocess.run([str(venv_py), str(script_path)] + sys.argv[1:])
    sys.exit(res.returncode)

if str(agent_dir) not in sys.path:
    sys.path.insert(0, str(agent_dir))
sys.path.insert(0, str(script_path.parent))

import deploy_all_chains

if __name__ == "__main__":
    deploy_all_chains.main()

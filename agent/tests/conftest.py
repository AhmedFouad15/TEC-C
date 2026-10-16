"""Shared fixtures. On-chain tests run against a throwaway Anvil chain and are skipped when Foundry is missing."""

import shutil
import socket
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def anvil_url():
    if shutil.which("anvil") is None:
        pytest.skip("anvil not installed (brew install foundry)")
    if not (REPO / "out" / "TetherGuardHook.sol" / "TetherGuardHook.json").exists():
        pytest.skip("contracts not built (run `forge build` in the repo root)")
    port = _free_port()
    proc = subprocess.Popen(
        ["anvil", "--port", str(port), "--host", "127.0.0.1", "--silent"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.skip("anvil did not start")
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
    proc.wait(timeout=5)

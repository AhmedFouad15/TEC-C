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


def _start_anvil(chain_id: int | None = None):
    anvil_bin = shutil.which("anvil")
    if not anvil_bin:
        foundry_anvil = Path.home() / ".foundry" / "bin" / "anvil.exe"
        if foundry_anvil.exists():
            anvil_bin = str(foundry_anvil)
    if not anvil_bin:
        pytest.skip("anvil not installed (brew install foundry)")
    if not (REPO / "contracts" / "out" / "TetherGuardHook.sol" / "TetherGuardHook.json").exists():
        pytest.skip("contracts not built (run `forge build` in contracts/)")
    port = _free_port()
    cmd = [anvil_bin, "--port", str(port), "--host", "127.0.0.1", "--disable-code-size-limit", "--silent"]
    if chain_id is not None:
        cmd += ["--chain-id", str(chain_id)]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    return proc, f"http://127.0.0.1:{port}"


@pytest.fixture(scope="session")
def anvil_url():
    proc, url = _start_anvil()
    yield url
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="session")
def arbitrum_like_url():
    """A second, independent local chain with Arbitrum Sepolia's chain id (421614): proves the Commodities
    executor sends real transactions on a different chain than Ethereum, exactly as it would on the testnet."""
    proc, url = _start_anvil(chain_id=421614)
    yield url
    proc.terminate()
    proc.wait(timeout=5)

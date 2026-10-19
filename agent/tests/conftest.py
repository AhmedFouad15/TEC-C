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


def _is_our_fresh_chain(proc: subprocess.Popen, port: int, chain_id: int | None) -> bool:
    """Our anvil process is alive and the node on the port is a brand-new chain with the expected id."""
    import json
    import urllib.request

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False  # anvil exited (e.g. port taken between _free_port and bind)
        try:
            def rpc(method):
                req = urllib.request.Request(f"http://127.0.0.1:{port}", headers={"Content-Type": "application/json"},
                                             data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": []}).encode())
                with urllib.request.urlopen(req, timeout=1) as r:
                    return int(json.loads(r.read())["result"], 16)

            return rpc("eth_blockNumber") == 0 and (chain_id is None or rpc("eth_chainId") == chain_id)
        except OSError:
            time.sleep(0.1)
    return False


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
    for _attempt in range(3):
        port = _free_port()
        cmd = [anvil_bin, "--port", str(port), "--host", "127.0.0.1", "--disable-code-size-limit", "--silent"]
        if chain_id is not None:
            cmd += ["--chain-id", str(chain_id)]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if _is_our_fresh_chain(proc, port, chain_id):
            break
        proc.kill()  # lost the port race, or something else answered on it: never test against a foreign node
    else:
        pytest.skip("anvil did not start on a free port")
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


@pytest.fixture(autouse=True)
def _simulated_markets_only():
    """API tests never reach a live node a developer may have deployed locally (agent/.state/markets): every test
    gets its own router with honest simulated markets and a fresh cross-chain tether tracker."""
    from tecc_brain.api.deps import get_anchors, get_router
    from tecc_brain.app import app
    from tecc_brain.onchain.anchoring import AuditAnchorService
    from tecc_brain.onchain.executor import MarketRouter

    router = MarketRouter(anchors=AuditAnchorService(None))
    app.dependency_overrides[get_router] = lambda: router
    app.dependency_overrides[get_anchors] = lambda: AuditAnchorService(None)
    yield router
    app.dependency_overrides.pop(get_router, None)
    app.dependency_overrides.pop(get_anchors, None)

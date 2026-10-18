"""Automated lifecycle manager for the local FISCO BCOS testnet cluster (Section 7).

Manages starting, probing, and stopping the 4-node FISCO BCOS testnet cluster
running inside WSL 2 (with Web3 JSON-RPC enabled on 127.0.0.1:8555).

Allows the application (FastAPI and Virtual Session runner) to start the node cluster
on demand when launched, connect the on-chain executors to the consortium network,
and cleanly stop the node cluster when shutting down.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

logger = logging.getLogger("tecc_brain.onchain.fisco_node")

DEFAULT_FISCO_RPC = "http://127.0.0.1:8555"
EXPECTED_CHAIN_ID_HEX = "0x4ee8"  # 20200 decimal
PID_FILE = Path(__file__).resolve().parents[2] / ".state" / "fisco_cluster.pid"

_proc_handle: subprocess.Popen | None = None


def is_fisco_node_running(rpc_url: str = DEFAULT_FISCO_RPC, timeout: float = 1.0) -> bool:
    """Probe the FISCO BCOS Web3 JSON-RPC endpoint with eth_chainId.

    Returns True if the endpoint answers with the testnet chain ID (0x4ee8 / 20200).
    """
    payload = json.dumps({"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1}).encode("utf-8")
    req = urllib.request.Request(
        rpc_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            result = data.get("result")
            if result and (str(result).lower() == EXPECTED_CHAIN_ID_HEX or int(str(result), 16) == 20200):
                return True
    except Exception:
        pass
    return False


def _has_wsl() -> bool:
    """Check if WSL executable is available on Windows."""
    return shutil.which("wsl") is not None or shutil.which("wsl.exe") is not None


def ensure_fisco_node_running(
    rpc_url: str = DEFAULT_FISCO_RPC,
    timeout: float = 15.0,
    wsl_distro: str = "Ubuntu",
) -> bool:
    """Ensure the FISCO BCOS node cluster is running and responding to RPC calls.

    If already responsive, returns False (indicating it was already active).
    If offline, starts a persistent WSL supervisor process to prevent the 15s idle timeout,
    and polls until the Web3 JSON-RPC endpoint is responsive.
    Returns True if successfully started by this call.
    """
    global _proc_handle

    if is_fisco_node_running(rpc_url=rpc_url):
        logger.info("[FISCO BCOS] Testnet cluster is already running at %s", rpc_url)
        return False

    logger.info("[FISCO BCOS] Testnet cluster is offline. Starting cluster via WSL...")

    if not _has_wsl():
        logger.warning("[FISCO BCOS] WSL is not detected in system PATH. Cannot auto-start node cluster.")
        return False

    # Start persistent supervisor process attached to WSL
    wsl_cmd = ["wsl", "-u", "root", "-d", wsl_distro, "--", "bash", "/home/ahmed/fisco/run_cluster.sh"]

    try:
        # Create .state dir if not present
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)

        creation_flags = 0
        if os.name == "nt":
            # DETACHED_PROCESS = 0x00000008, CREATE_NEW_PROCESS_GROUP = 0x00000200
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

        _proc_handle = subprocess.Popen(
            wsl_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        PID_FILE.write_text(str(_proc_handle.pid), encoding="utf-8")
        logger.info("[FISCO BCOS] Launched supervisor process with PID %d", _proc_handle.pid)
    except Exception as exc:
        logger.error("[FISCO BCOS] Failed to launch WSL process: %s", exc)
        return False

    # Poll until responding or timeout
    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout:
        if is_fisco_node_running(rpc_url=rpc_url):
            logger.info("[FISCO BCOS] Testnet cluster successfully started and ready at %s", rpc_url)
            return True
        time.sleep(0.5)

    logger.error("[FISCO BCOS] Failed to reach testnet cluster within %.1f seconds.", timeout)
    return False


def stop_fisco_node(
    timeout: float = 10.0,
    wsl_distro: str = "Ubuntu",
) -> bool:
    """Stop the FISCO BCOS testnet cluster cleanly.

    Terminates the persistent supervisor process and stops all 4 node processes in WSL.
    """
    global _proc_handle

    logger.info("[FISCO BCOS] Stopping testnet cluster...")
    if not _has_wsl():
        return False

    # 1. Terminate in-memory process handle
    if _proc_handle is not None:
        try:
            _proc_handle.terminate()
            _proc_handle.wait(timeout=3)
        except Exception:
            pass
        _proc_handle = None

    # 2. Terminate PID from PID_FILE if present
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text(encoding="utf-8").strip())
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, 9)
        except Exception:
            pass
        try:
            PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    # 3. Stop nodes inside WSL
    wsl_cmd = ["wsl", "-u", "root", "-d", wsl_distro, "--"]
    try:
        subprocess.run(
            [*wsl_cmd, "bash", "-c", "/home/ahmed/fisco/nodes/127.0.0.1/stop_all.sh && pkill -9 -f run_cluster.sh || true"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        logger.debug("[FISCO BCOS] stop command exception: %s", exc)

    # 4. Verify stopped
    start_time = time.monotonic()
    while time.monotonic() - start_time < timeout:
        if not is_fisco_node_running():
            logger.info("[FISCO BCOS] Testnet cluster successfully stopped.")
            return True
        time.sleep(0.3)

    return not is_fisco_node_running()


@contextmanager
def fisco_node_scope(
    rpc_url: str = DEFAULT_FISCO_RPC,
    timeout: float = 15.0,
    auto_stop: bool = True,
) -> Generator[bool, None, None]:
    """Context manager to ensure the node is running for a block of code, stopping it on exit if newly started."""
    newly_started = ensure_fisco_node_running(rpc_url=rpc_url, timeout=timeout)
    try:
        yield newly_started
    finally:
        if newly_started and auto_stop:
            stop_fisco_node()

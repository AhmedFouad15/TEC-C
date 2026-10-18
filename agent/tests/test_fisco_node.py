from io import BytesIO
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from tecc_brain.onchain.fisco_node import (
    DEFAULT_FISCO_RPC,
    ensure_fisco_node_running,
    fisco_node_scope,
    is_fisco_node_running,
    stop_fisco_node,
)


def test_is_fisco_node_running_success():
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"jsonrpc":"2.0","result":"0x4ee8","id":1}'
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert is_fisco_node_running("http://127.0.0.1:8555") is True


def test_is_fisco_node_running_connection_refused():
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        assert is_fisco_node_running("http://127.0.0.1:8555") is False


def test_is_fisco_node_running_wrong_chain_id():
    mock_resp = MagicMock()
    mock_resp.read.return_value = b'{"jsonrpc":"2.0","result":"0x1","id":1}'
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert is_fisco_node_running("http://127.0.0.1:8555") is False


def test_ensure_fisco_node_running_already_active():
    with patch("tecc_brain.onchain.fisco_node.is_fisco_node_running", return_value=True):
        started = ensure_fisco_node_running()
        assert started is False


def test_ensure_fisco_node_running_no_wsl():
    with patch("tecc_brain.onchain.fisco_node.is_fisco_node_running", return_value=False), \
         patch("tecc_brain.onchain.fisco_node._has_wsl", return_value=False):
        started = ensure_fisco_node_running()
        assert started is False


def test_ensure_fisco_node_running_starts_via_wsl():
    states = [False, True]

    def mock_probe(*args, **kwargs):
        if states:
            return states.pop(0)
        return True

    mock_proc = MagicMock()
    mock_proc.pid = 12345

    with patch("tecc_brain.onchain.fisco_node.is_fisco_node_running", side_effect=mock_probe), \
         patch("tecc_brain.onchain.fisco_node._has_wsl", return_value=True), \
         patch("subprocess.Popen", return_value=mock_proc) as mock_popen, \
         patch("pathlib.Path.write_text"):
        started = ensure_fisco_node_running(timeout=2.0)
        assert started is True
        assert mock_popen.called


def test_stop_fisco_node_stops_cleanly():
    with patch("tecc_brain.onchain.fisco_node._has_wsl", return_value=True), \
         patch("tecc_brain.onchain.fisco_node.is_fisco_node_running", return_value=False), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        stopped = stop_fisco_node(timeout=2.0)
        assert stopped is True
        assert mock_run.called


def test_fisco_node_scope_context_manager():
    with patch("tecc_brain.onchain.fisco_node.ensure_fisco_node_running", return_value=True) as mock_start, \
         patch("tecc_brain.onchain.fisco_node.stop_fisco_node", return_value=True) as mock_stop:
        with fisco_node_scope() as started:
            assert started is True
        assert mock_start.called
        assert mock_stop.called

from unittest.mock import MagicMock, patch
import pytest

from tecc_brain.onchain.audit_anchor import (
    AuditRecordType,
    PrivacyAuditAnchorClient,
    compute_audit_record_hash,
)


def test_compute_audit_record_hash():
    h1 = compute_audit_record_hash("0x1234", "stETH", "DEPOSIT", 0.985, timestamp=1700000000, salt="salt1")
    assert h1.startswith("0x")
    assert len(h1) == 66

    # Deterministic
    h2 = compute_audit_record_hash("0x1234", "stETH", "DEPOSIT", 0.985, timestamp=1700000000, salt="salt1")
    assert h1 == h2

    # Different salt
    h3 = compute_audit_record_hash("0x1234", "stETH", "DEPOSIT", 0.985, timestamp=1700000000, salt="salt2")
    assert h1 != h3


def test_privacy_audit_anchor_client_submit_and_verify():
    mock_rpc = MagicMock()
    mock_rpc.chain_id.return_value = 20200
    mock_rpc.call.return_value = "0x5208"
    mock_rpc.fee_fields.return_value = {"maxFeePerGas": 0, "maxPriorityFeePerGas": 0}
    mock_rpc.send_raw.return_value = {"transactionHash": "0x1122334455"}

    key = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    anchor_addr = "0x9999999999999999999999999999999999999999"

    client = PrivacyAuditAnchorClient(mock_rpc, anchor_addr, signer_key=key)
    record_hash = compute_audit_record_hash("0x1234", "stETH", "DEPOSIT", 0.985, 1700000000)

    with patch.object(client.contract, "encode", return_value=b"\x00" * 36):
        tx_hash = client.anchor_record(record_hash, AuditRecordType.DEPEG_DETECTED)
        assert tx_hash == "0x1122334455"
        assert mock_rpc.send_raw.called

    with patch.object(client.contract, "call", return_value=[True, 1700000000]):
        is_anchored, ts = client.verify_record(record_hash)
        assert is_anchored is True
        assert ts == 1700000000

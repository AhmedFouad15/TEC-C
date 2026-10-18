"""Unit tests for Cross-Chain Bridge Relayer service."""

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct

from tecc_brain.onchain.relayer import (
    CrossChainBridgeRelayer,
    CrossChainSpendProof,
    PeerChainConfig,
    compute_proof_message_hash,
    sign_spend_proof,
)

# Test keys
ROOT_OWNER_KEY = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
TEST_ACCOUNT = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
HOOK_ETH = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
HOOK_ARB = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"


def test_spend_proof_creation_and_properties():
    proof = CrossChainSpendProof.create(
        account=TEST_ACCOUNT,
        source_chain_id=1,
        amount_usd=250.0,
        epoch=10,
        nonce=42,
    )
    assert proof.amount_usd == 250.0
    assert proof.amount_usd_raw == 250 * 10**8
    assert proof.source_chain_id == 1
    assert proof.epoch == 10
    assert proof.nonce == 42
    assert len(proof.to_tuple()) == 6


def test_signature_recovery_matches_signer():
    proof = CrossChainSpendProof.create(
        account=TEST_ACCOUNT,
        source_chain_id=1,
        amount_usd=500.0,
        epoch=100,
        nonce=1,
    )
    signer = Account.from_key(ROOT_OWNER_KEY)
    sig = sign_spend_proof(proof, dest_chain_id=42161, dest_hook_address=HOOK_ARB, signer_key=ROOT_OWNER_KEY)
    assert len(sig) == 65

    # Verify signature recovers signer address
    msg_hash = compute_proof_message_hash(proof, dest_chain_id=42161, dest_hook_address=HOOK_ARB)
    signable = encode_defunct(primitive=msg_hash)
    recovered = Account.recover_message(signable, signature=sig)
    assert recovered.lower() == signer.address.lower()


def test_digest_differs_per_destination_chain_and_hook():
    proof = CrossChainSpendProof.create(
        account=TEST_ACCOUNT,
        source_chain_id=1,
        amount_usd=500.0,
        epoch=100,
        nonce=1,
    )
    hash_arb = compute_proof_message_hash(proof, dest_chain_id=42161, dest_hook_address=HOOK_ARB)
    hash_fisco = compute_proof_message_hash(proof, dest_chain_id=2026, dest_hook_address=HOOK_ARB)
    hash_diff_hook = compute_proof_message_hash(proof, dest_chain_id=42161, dest_hook_address=HOOK_ETH)

    assert hash_arb != hash_fisco
    assert hash_arb != hash_diff_hook


def test_relayer_nonce_progression():
    relayer = CrossChainBridgeRelayer(relayer_key=ROOT_OWNER_KEY)
    n1 = relayer._next_nonce(TEST_ACCOUNT)
    n2 = relayer._next_nonce(TEST_ACCOUNT)
    n3 = relayer._next_nonce(TEST_ACCOUNT)
    assert n2 == n1 + 1
    assert n3 == n2 + 1


def test_relayer_peer_registration():
    relayer = CrossChainBridgeRelayer(relayer_key=ROOT_OWNER_KEY)
    relayer.register_peer(PeerChainConfig(
        chain_id=42161,
        network_name="Arbitrum One",
        rpc_url="https://arb1.arbitrum.io/rpc",
        hook_address=HOOK_ARB,
    ))
    assert 42161 in relayer.peer_chains
    assert relayer.peer_chains[42161].network_name == "Arbitrum One"

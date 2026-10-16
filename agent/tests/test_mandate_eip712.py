import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak

from tecc_brain.onchain.mandate import UserMandate, policy_hash
from tecc_brain.onchain.session import SIGNATURE_LENGTH, session_signature

VALIDATOR = "0x5FbDB2315678afecb367f032d93F642f64180aa3"
ACCOUNT = "0x" + "ab" * 20
KEY = Account.create()


def mandate(**kw):
    base = dict(account=ACCOUNT, session_key=KEY.address, max_amount_usd=1000.0, valid_after=1_700_000_000,
                valid_until=1_700_086_400, risk_tier=2, policy=policy_hash(["aave_v3_usdc", "lido_stake"]))
    return UserMandate(**{**base, **kw})


def test_digest_matches_eth_account_typed_data():
    m = mandate()
    signable = encode_typed_data(full_message=m.typed_data(31337, VALIDATOR))
    expected = keccak(b"\x19" + signable.version + signable.header + signable.body)
    assert m.digest(31337, VALIDATOR) == expected


@pytest.mark.parametrize("change", [
    {"max_amount_usd": 1001.0}, {"valid_until": 1_700_086_401}, {"risk_tier": 3},
    {"policy": policy_hash(["aave_v3_usdc"])}, {"session_key": "0x" + "cd" * 20},
])
def test_every_field_is_committed(change):
    assert mandate(**change).digest(31337, VALIDATOR) != mandate().digest(31337, VALIDATOR)


def test_digest_is_bound_to_chain_and_validator():
    m = mandate()
    assert m.digest(1, VALIDATOR) != m.digest(31337, VALIDATOR)
    assert m.digest(31337, "0x" + "11" * 20) != m.digest(31337, VALIDATOR)


def test_policy_hash_ignores_order():
    assert policy_hash(["b", "a"]) == policy_hash(["a", "b"])


def test_amount_is_in_eight_decimal_usd():
    assert mandate(max_amount_usd=500.0).message()["maxAmountUsd"] == 500 * 10**8


def test_session_signature_layout_is_117_bytes():
    digest = mandate().digest(31337, VALIDATOR)
    sig = session_signature(KEY.key, keccak(b"calldata"), digest)
    assert len(sig) == SIGNATURE_LENGTH == 117
    assert sig[:20] == bytes.fromhex(KEY.address[2:])
    assert sig[85:] == digest
    assert sig[84] in (27, 28)

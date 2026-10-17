"""Session keys: the only key the Brain ever holds. Provisioned by the owner, bound to one mandate, revocable.

Provisioning (owner = the FaceID passkey holder; Anvil account 0 locally):
1. open the 5-minute biometric window (the next call breaks the tether: the validator is not a whitelisted target);
2. through the account, register the key on SessionKeyValidator with mandateRoot = the UserMandate digest;
3. authorise the key on TetherGuardHook (heartbeat and radius levers);
4. install the key as an ERC-7579 executor on TecAccount: with no bundler this is how it reaches `execute`,
   and every call still passes the hook's preCheck/postCheck;
5. close the biometric window and fund the key with gas (a paymaster would sponsor this in production).
"""

from __future__ import annotations

from eth_account import Account
from eth_account.messages import encode_defunct

from tecc_brain.onchain.artifacts import Contract
from tecc_brain.onchain.deploy import LocalDeployment
from tecc_brain.onchain.mandate import UserMandate
from tecc_brain.onchain.rpc import Rpc

SIGNATURE_LENGTH = 117  # sessionKey (20) ‖ ECDSA (65) ‖ mandateDigest (32)
MODULE_TYPE_EXECUTOR = 2
GAS_FUNDING_WEI = 10**18


def execution_calldata(target: str, value: int, data: bytes) -> bytes:
    """TecAccount execution layout: target (20) ‖ value (32) ‖ callData."""
    return bytes.fromhex(target[2:]) + value.to_bytes(32, "big") + data


def session_signature(private_key: bytes | str, hash32: bytes, mandate_digest: bytes) -> bytes:
    signer = Account.from_key(private_key)
    signed = Account.sign_message(encode_defunct(primitive=hash32), private_key)
    sig = bytes(signed.signature)
    assert len(sig) == 65 and len(mandate_digest) == 32
    return bytes.fromhex(signer.address[2:]) + sig + mandate_digest


def provision_session_key(
    rpc: Rpc, dep: LocalDeployment, mandate: UserMandate, fund_wei: int = GAS_FUNDING_WEI,
    owner_key: bytes | str | None = None,
) -> None:
    """`owner_key` signs as the root owner on real networks; on Anvil the owner is a node-managed account."""
    owner = dep.root_owner
    k = owner_key
    hook = Contract.load("TetherGuardHook", dep.hook)
    validator = Contract.load("SessionKeyValidator", dep.validator)
    account = Contract.load("TecAccount", dep.account)
    digest = mandate.digest(dep.chain_id, dep.validator)

    hook.transact(rpc, "completeBiometricVerification", dep.account, sender=owner, key=k)
    register = validator.encode(
        "registerSessionKey", dep.account, mandate.session_key, mandate.valid_after, mandate.valid_until, digest
    )
    account.transact(rpc, "execute", b"\x00" * 32, execution_calldata(dep.validator, 0, register), sender=owner, key=k)
    hook.transact(rpc, "setSessionKeyAuthorization", dep.account, mandate.session_key, True, sender=owner, key=k)
    account.transact(rpc, "installModule", MODULE_TYPE_EXECUTOR, mandate.session_key, b"", sender=owner, key=k)
    hook.transact(rpc, "revokeBiometricVerification", dep.account, sender=owner, key=k)
    if fund_wei:
        rpc.send({"from": owner, "to": mandate.session_key, "value": hex(fund_wei)}, k)

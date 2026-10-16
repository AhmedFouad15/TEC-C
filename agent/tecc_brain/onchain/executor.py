"""The Web3 Executor: turns an ExecutionIntent into a vault-checked transaction signed by the session key.

Order of checks, cheapest first; nothing is sent unless all pass:
1. the amount fits the owner's mandate (off-chain);
2. Ahmed's SessionKeyValidator accepts the 117-byte session signature over keccak(executionCalldata), i.e. the key
   is active, inside its time window and bound to this mandate (ERC-1271 view call);
3. a dry run of `account.execute` from the session key passes the hook (radius, whitelist, tier, heartbeat);
then the signed transaction is sent and the Morning Review record id is read from AutonomousExecutionLogged.
"""

from __future__ import annotations

import json
from pathlib import Path

from eth_account import Account
from eth_utils import keccak
from pydantic import BaseModel

from tecc_brain.models import ExecutionIntent, usd_to_onchain
from tecc_brain.onchain.artifacts import Contract
from tecc_brain.onchain.deploy import USDC_DECIMALS, LocalDeployment
from tecc_brain.onchain.mandate import UserMandate
from tecc_brain.onchain.rpc import Rpc, RpcError
from tecc_brain.onchain.session import execution_calldata, session_signature

ERC1271_MAGIC = bytes.fromhex("1626ba7e")
LEDGER_FILE = Path(__file__).resolve().parents[2] / ".state" / "records.local.json"


class LedgerRecord(BaseModel):
    record_id: int
    venue_id: str
    amount_usd: float
    tx_hash: str


class RecordLedger:
    """recordId → what the Brain did, so on-chain reviews can be attributed to a venue and a USD amount."""

    def __init__(self, path: Path = LEDGER_FILE) -> None:
        self.path = Path(path)

    def _read(self) -> dict[str, dict]:
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def add(self, record: LedgerRecord) -> None:
        data = self._read()
        data[str(record.record_id)] = record.model_dump()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get(self, record_id: int) -> LedgerRecord | None:
        raw = self._read().get(str(record_id))
        return LedgerRecord.model_validate(raw) if raw else None


class ChainExecutor:
    def __init__(
        self, rpc: Rpc, dep: LocalDeployment, session_key: bytes | str, mandate: UserMandate,
        ledger: RecordLedger | None = None,
    ) -> None:
        self.rpc, self.dep, self.mandate = rpc, dep, mandate
        self.key = Account.from_key(session_key)
        self.ledger = ledger or RecordLedger()
        self.hook = Contract.load("TetherGuardHook", dep.hook)
        self.validator = Contract.load("SessionKeyValidator", dep.validator)
        self.account = Contract.load("TecAccount", dep.account)
        self.usdc = Contract.load("MockERC20", dep.usdc)
        self.protocol = Contract.load("MockDeFiProtocol")

    # --- building ------------------------------------------------------------------------------

    def _execution(self, intent: ExecutionIntent) -> bytes:
        venue = self.dep.venues.get(intent.venue_id)
        if venue is None:
            raise ValueError(f"venue {intent.venue_id} is not deployed on this chain")
        if intent.asset_in == "USDC":
            units = round(intent.amount_usd * 10**USDC_DECIMALS)
            return execution_calldata(self.dep.usdc, 0, self.usdc.encode("transfer", venue, units))
        if intent.asset_in == "ETH":
            wei = int(intent.amount_usd / self.dep.eth_usd * 10**18)
            return execution_calldata(venue, wei, self.protocol.encode("stake"))
        raise ValueError(f"{intent.asset_in} is not mocked on the local chain (USDC and ETH are)")

    def _reason(self, err: RpcError) -> str:
        data = err.data
        decoded = self.account.decode_error(data)
        if decoded and decoded.startswith("ExecutionFailed") and data:
            from eth_abi import decode

            inner = "0x" + decode(["bytes"], bytes.fromhex(data[10:]))[0].hex()
            data, decoded = inner, None
        for contract in (self.hook, self.validator, self.usdc, self.account):
            decoded = decoded or contract.decode_error(data)
        return decoded or err.message

    # --- submitting ----------------------------------------------------------------------------

    def submit(self, intent: ExecutionIntent, account: str) -> ExecutionIntent:
        def failed(detail: str) -> ExecutionIntent:
            return intent.model_copy(update={"status": "failed", "detail": detail})

        if usd_to_onchain(intent.amount_usd) > usd_to_onchain(self.mandate.max_amount_usd):
            return failed(f"${intent.amount_usd:,.0f} exceeds the owner's mandate (max ${self.mandate.max_amount_usd:,.0f})")
        try:
            calldata = self._execution(intent)
        except ValueError as exc:
            return failed(str(exc))

        digest = self.mandate.digest(self.dep.chain_id, self.dep.validator)
        sig = session_signature(self.key.key, keccak(calldata), digest)
        try:
            magic = self.validator.call(self.rpc, "isValidSignatureWithSender", self.dep.account, keccak(calldata), sig)[0]
        except RpcError as exc:
            return failed(f"validator pre-flight error: {self._reason(exc)}")
        if magic != ERC1271_MAGIC:
            return failed("session signature rejected by the validator (inactive key, expired, or a different mandate)")

        data = "0x" + self.account.encode("execute", b"\x00" * 32, calldata).hex()
        tx = {"from": self.key.address, "to": self.dep.account, "data": data}
        try:
            self.rpc.call("eth_call", [tx, "latest"])
            gas = int(self.rpc.call("eth_estimateGas", [tx]), 16)
        except RpcError as exc:
            return failed(f"refused by the vault: {self._reason(exc)}")

        gas_price = int(self.rpc.call("eth_gasPrice"), 16)
        signed = Account.sign_transaction({
            "type": 2, "chainId": self.dep.chain_id, "to": self.dep.account, "data": data, "value": 0,
            "nonce": int(self.rpc.call("eth_getTransactionCount", [self.key.address, "pending"]), 16),
            "gas": int(gas * 1.25), "maxFeePerGas": gas_price * 2, "maxPriorityFeePerGas": min(gas_price, 10**9),
        }, self.key.key)
        try:
            receipt = self.rpc.send_raw("0x" + bytes(signed.raw_transaction).hex())
        except RpcError as exc:
            return failed(f"transaction failed: {self._reason(exc)}")

        records = [a["recordId"] for name, a, _ in self.hook.decode_logs(receipt["logs"]) if name == "AutonomousExecutionLogged"]
        record_id = records[0] if records else None
        if record_id is not None:
            self.ledger.add(LedgerRecord(record_id=record_id, venue_id=intent.venue_id, amount_usd=intent.amount_usd,
                                         tx_hash=receipt["transactionHash"]))
        return intent.model_copy(update={
            "status": "submitted", "tx_hash": receipt["transactionHash"],
            "target_address": self.dep.venues[intent.venue_id],
            "detail": f"vault accepted; Morning Review record #{record_id}" if record_id else "vault accepted",
        })

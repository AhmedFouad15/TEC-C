"""Make a market live: deploy the vault suite on its chain, provision the Brain's session key, record it.

    # local Anvil (no key needed: Anvil's account 0 signs)
    .venv/bin/python scripts/deploy_market_chain.py --network anvil --rpc http://127.0.0.1:8545

    # Arbitrum Sepolia / FISCO BCOS: a funded deployer key in an environment variable (never on the command line)
    export TECC_DEPLOYER_KEY=0x...            # becomes the vault's root owner for the demo
    .venv/bin/python scripts/deploy_market_chain.py --network arbitrum --rpc https://sepolia-rollup.arbitrum.io/rpc
    .venv/bin/python scripts/deploy_market_chain.py --network fisco_bcos --rpc http://127.0.0.1:8545 --no-native-coin

    # then prove it with one real, vault-checked transaction
    .venv/bin/python scripts/deploy_market_chain.py --network arbitrum --smoke 25 --smoke-venue paxg_hold

Step-by-step guide: agent/MULTICHAIN_NODES.md.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eth_account import Account  # noqa: E402

from tecc_brain.models import ActionType, CardLabel, ExecutionIntent, usd_to_onchain  # noqa: E402
from tecc_brain.onchain.deploy import deploy_local  # noqa: E402
from tecc_brain.onchain.mandate import UserMandate, policy_hash  # noqa: E402
from tecc_brain.onchain.markets import NETWORKS, MarketFile, build_router, load_market, save_market  # noqa: E402
from tecc_brain.onchain.rpc import Rpc  # noqa: E402

MARKET_OF = {"anvil": "crypto", "sepolia": "crypto", "arbitrum": "commodities", "fisco_bcos": "chinese_market"}
RPC_ENV = {"anvil": "TECC_ANVIL_RPC_URL", "sepolia": "SEPOLIA_RPC_URL", "arbitrum": "ARBITRUM_RPC_URL",
           "fisco_bcos": "FISCO_BCOS_RPC_URL"}


def eth(x: float) -> int:
    return int(x * 10**18)


def deploy(args: argparse.Namespace) -> None:
    if args.network == "fisco_bcos":
        from tecc_brain.onchain.fisco_node import ensure_fisco_node_running
        ensure_fisco_node_running(args.rpc or "http://127.0.0.1:8555")

    rpc_url = args.rpc or os.environ.get(RPC_ENV[args.network]) or (
        "http://127.0.0.1:8545" if args.network == "anvil" else ("http://127.0.0.1:8555" if args.network == "fisco_bcos" else None)
    )
    if not rpc_url:
        sys.exit(f"pass --rpc or set {RPC_ENV[args.network]}")
    rpc = Rpc(rpc_url, timeout_s=60)
    key = os.environ.get(args.deployer_key_env)
    if key is None and args.network != "anvil":
        env_file = Path(__file__).resolve().parents[1] / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("TECC_DEPLOYER_KEY="):
                    val = line.split("=", 1)[1].strip().strip("'\"")
                    if val and not val.startswith("your_") and not val.startswith("0x..."):
                        key = val
                        break
        if key is None:
            wallet_f = Path(__file__).resolve().parents[1] / ".state" / "wallet.json"
            if wallet_f.exists():
                try:
                    wdata = json.loads(wallet_f.read_text(encoding="utf-8"))
                    key = wdata.get("private_key")
                except Exception:
                    pass
    if key is None and args.network != "anvil":
        sys.exit(f"set {args.deployer_key_env} to a funded private key for {args.network} (it becomes the demo root owner)")
    chain_id = rpc.chain_id()
    owner = Account.from_key(key).address if key else rpc.call("eth_accounts")[0]
    print(f"[{args.network}] chain id {chain_id}, deployer/root owner {owner}")

    native = not args.no_native_coin
    dep = deploy_local(
        rpc, eth_usd=args.eth_usd, radius_usd=args.radius, ceiling_usd=args.ceiling, tier=args.tier,
        deployer_key=key, fund_eth_wei=eth(args.fund_account_eth) if native else 0,
    )
    session = Account.create()
    now = rpc.block_timestamp()
    mandate = UserMandate(
        account=dep.account, session_key=session.address, max_amount_usd=args.mandate_max, valid_after=now - 60,
        valid_until=now + int(args.days * 86400), risk_tier=args.tier, policy=policy_hash(sorted(dep.venues)),
    )
    from tecc_brain.onchain.session import provision_session_key

    provision_session_key(rpc, dep, mandate, fund_wei=eth(args.fund_session_eth) if native else 0, owner_key=key)
    path = save_market(MarketFile(network=args.network, rpc_url=rpc_url, deployment=dep, mandate=mandate,
                                  session_key="0x" + bytes(session.key).hex()))
    print(f"  TecAccount          {dep.account}")
    print(f"  TetherGuardHook     {dep.hook}")
    print(f"  SessionKeyValidator {dep.validator}")
    print(f"  session key         {session.address}  (mandate max ${args.mandate_max:,.0f}, {args.days:g} days)")
    print(f"  saved               {path}  (owner-only file; contains the session key)")
    print(f"The {MARKET_OF[args.network]} market is now LIVE for the Brain.")


def smoke(args: argparse.Namespace) -> None:
    if args.network == "fisco_bcos":
        from tecc_brain.onchain.fisco_node import ensure_fisco_node_running
        ensure_fisco_node_running(args.rpc or "http://127.0.0.1:8555")

    m = load_market(args.network)
    if m is None:
        sys.exit(f"{args.network} is not deployed yet: run this script without --smoke first")
    os.environ.setdefault("TECC_NETWORK", args.network if MARKET_OF[args.network] == "crypto" else "anvil")
    router = build_router(daily_limit_usd=args.radius, crypto_network=args.network)
    intent = ExecutionIntent(
        card_label=CardLabel.BETTER, venue_id=args.smoke_venue, action=ActionType.DEPOSIT, asset_in="USDC",
        amount_usd=args.smoke, amount_onchain=usd_to_onchain(args.smoke), market=MARKET_OF[args.network],
    )
    out = router.submit(intent, m.deployment.account)
    print(f"status   {out.status}\ntx hash  {out.tx_hash}\ndetail   {out.detail}")
    if out.status != "submitted":
        sys.exit(1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--network", choices=NETWORKS, required=True)
    p.add_argument("--rpc", help="node URL (http://127.0.0.1:… or https://…)")
    p.add_argument("--deployer-key-env", default="TECC_DEPLOYER_KEY", help="env var holding the funded deployer key")
    p.add_argument("--eth-usd", type=float, default=2500.0, help="price for the mock ETH/USD feed")
    p.add_argument("--radius", type=float, default=500.0, help="daily tether radius, USD")
    p.add_argument("--ceiling", type=float, default=2000.0, help="elastic ceiling, USD")
    p.add_argument("--tier", type=int, default=2, choices=(1, 2, 3))
    p.add_argument("--mandate-max", type=float, default=1000.0, help="max USD per Brain action in the mandate")
    p.add_argument("--days", type=float, default=7.0, help="session key validity")
    p.add_argument("--fund-account-eth", type=float, default=None, help="native coin sent to the vault account")
    p.add_argument("--fund-session-eth", type=float, default=None, help="gas money for the session key")
    p.add_argument("--no-native-coin", action="store_true", help="chain has no native coin / zero gas (FISCO BCOS)")
    p.add_argument("--smoke", type=float, help="instead of deploying: send one real USDC deposit of this size")
    p.add_argument("--smoke-venue", default="aave_v3_usdc")
    args = p.parse_args()
    local = args.network == "anvil"
    if args.fund_account_eth is None:
        args.fund_account_eth = 10.0 if local else 0.0
    if args.fund_session_eth is None:
        args.fund_session_eth = 1.0 if local else 0.002
    smoke(args) if args.smoke else deploy(args)


if __name__ == "__main__":
    main()

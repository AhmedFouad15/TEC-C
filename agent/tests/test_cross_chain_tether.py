import pytest
from tecc_brain.models import ActionType, CardLabel, ExecutionIntent, usd_to_onchain
from tecc_brain.onchain.executor import (
    ArbitrumCommoditiesExecutor,
    CrossChainTetherTracker,
    FiscoBcosExecutor,
    MarketRouter,
    PegGuardArbitrageExecutor,
)


def sample_intent(
    venue_id: str = "aave_v3_usdc",
    usd: float = 250.0,
    asset: str = "USDC",
    action: ActionType = ActionType.DEPOSIT,
    market: str = "crypto",
) -> ExecutionIntent:
    return ExecutionIntent(
        card_label=CardLabel.BEST,
        venue_id=venue_id,
        action=action,
        asset_in=asset,
        amount_usd=usd,
        amount_onchain=usd_to_onchain(usd),
        market=market,
    )


class MockCryptoExecutor:
    """Mock Ethereum executor for fast offline testing."""
    market = "crypto"

    def submit(self, intent: ExecutionIntent, account: str) -> ExecutionIntent:
        return intent.model_copy(update={
            "status": "submitted",
            "market": "crypto",
            "tx_hash": "0xeth_tx_hash_12345",
            "detail": "Ethereum Mainnet: executed on Uniswap/Lido",
        })


class MockMarketExecutor:
    """Stands in for a live market executor in tracker-only tests (no chain needed)."""

    def __init__(self, market: str) -> None:
        self.market = market

    def submit(self, intent: ExecutionIntent, account: str) -> ExecutionIntent:
        return intent.model_copy(update={"status": "submitted", "market": self.market, "tx_hash": "0x" + "ab" * 32})


def test_cross_chain_tracker_initial_state():
    """Initially tracker has 0 spent and full remaining allowance."""
    tracker = CrossChainTetherTracker(daily_limit_usd=500.0)
    assert tracker.get_spent("alice") == 0.0
    assert tracker.get_remaining("alice") == 500.0
    can_tx, _ = tracker.check_can_transact("alice", 500.0)
    assert can_tx is True


def test_cross_chain_full_spend_on_ethereum_locks_all_chains():
    """CORE REQUIREMENT:
    If the brain spent $500 on ETH and the limit is $500, it cannot transact on any of the 3
    (Ethereum, Arbitrum, FISCO BCOS).
    """
    tracker = CrossChainTetherTracker(daily_limit_usd=500.0)
    eth_exec = MockCryptoExecutor()
    fisco_exec = FiscoBcosExecutor()
    arb_exec = ArbitrumCommoditiesExecutor()

    router = MarketRouter(
        crypto=eth_exec,
        chinese_market=fisco_exec,
        commodities=arb_exec,
        tether_tracker=tracker,
        daily_limit_usd=500.0,
    )

    account = "0xUserSmartAccount1111"

    # 1. Spend full $500 on Ethereum (crypto)
    eth_intent = sample_intent(venue_id="uniswap_v3", usd=500.0, market="crypto")
    res_eth = router.submit(eth_intent, account)
    assert res_eth.status == "submitted"
    assert tracker.get_spent(account) == 500.0
    assert tracker.get_remaining(account) == 0.0

    # 2. Cannot transact on Arbitrum (commodities)
    arb_intent = sample_intent(venue_id="paxg_gold", usd=1.0, market="commodities")
    res_arb = router.submit(arb_intent, account)
    assert res_arb.status == "failed"
    assert "Cross-chain tether limit exceeded" in res_arb.detail
    assert "spent $500.00 / $500.00 across all chains" in res_arb.detail

    # 3. Cannot transact on FISCO BCOS (chinese_market)
    fisco_intent = sample_intent(venue_id="shibor_mmf", usd=1.0, market="chinese_market")
    res_fisco = router.submit(fisco_intent, account)
    assert res_fisco.status == "failed"
    assert "Cross-chain tether limit exceeded" in res_fisco.detail

    # 4. Cannot transact further on Ethereum (crypto)
    eth_intent_2 = sample_intent(venue_id="lido_steth", usd=5.0, market="crypto")
    res_eth_2 = router.submit(eth_intent_2, account)
    assert res_eth_2.status == "failed"
    assert "Cross-chain tether limit exceeded" in res_eth_2.detail


def test_cross_chain_split_spend_locks_remaining():
    """Multi-chain split spend:
    $200 on Ethereum + $250 on Arbitrum = $450 spent.
    Can only spend up to $50 on FISCO BCOS before being locked.
    """
    tracker = CrossChainTetherTracker(daily_limit_usd=500.0)
    eth_exec = MockCryptoExecutor()
    fisco_exec = MockMarketExecutor("chinese_market")
    arb_exec = MockMarketExecutor("commodities")

    router = MarketRouter(
        crypto=eth_exec,
        chinese_market=fisco_exec,
        commodities=arb_exec,
        tether_tracker=tracker,
        daily_limit_usd=500.0,
    )

    account = "0xUserSmartAccount2222"

    # Step 1: $200 on Ethereum
    res1 = router.submit(sample_intent(usd=200.0, market="crypto"), account)
    assert res1.status == "submitted"
    assert tracker.get_remaining(account) == 300.0

    # Step 2: $250 on Arbitrum
    res2 = router.submit(sample_intent(usd=250.0, market="commodities"), account)
    assert res2.status == "submitted"
    assert tracker.get_remaining(account) == 50.0

    # Step 3: Attempt $60 on FISCO BCOS -> REJECTED (exceeds $50 remaining)
    res3_fail = router.submit(sample_intent(usd=60.0, market="chinese_market"), account)
    assert res3_fail.status == "failed"
    assert "Cross-chain tether limit exceeded" in res3_fail.detail

    # Step 4: Spend exactly remaining $50 on FISCO BCOS -> SUCCEEDS
    res3_ok = router.submit(sample_intent(usd=50.0, market="chinese_market"), account)
    assert res3_ok.status == "submitted"
    assert tracker.get_remaining(account) == 0.0

    # Step 5: Now all 3 chains are completely locked
    for mkt in ("crypto", "commodities", "chinese_market"):
        res_lock = router.submit(sample_intent(usd=1.0, market=mkt), account)
        assert res_lock.status == "failed"


def test_cross_chain_epoch_rollover():
    """Advancing epoch resets the cross-chain spent counter to 0."""
    tracker = CrossChainTetherTracker(daily_limit_usd=500.0)
    account = "0xUserSmartAccount3333"

    # Day 1 (epoch 100)
    tracker.record_spend(account, "crypto", 500.0, epoch=100)
    assert tracker.get_remaining(account, epoch=100) == 0.0

    # Day 2 (epoch 101)
    assert tracker.get_spent(account, epoch=101) == 0.0
    assert tracker.get_remaining(account, epoch=101) == 500.0
    can_tx, _ = tracker.check_can_transact(account, 500.0, epoch=101)
    assert can_tx is True


def test_cross_chain_account_isolation():
    """Spending by Account A does not restrict Account B."""
    tracker = CrossChainTetherTracker(daily_limit_usd=500.0)
    alice = "0xAlice"
    bob = "0xBob"

    # Alice spends $500
    tracker.record_spend(alice, "crypto", 500.0)
    assert tracker.get_remaining(alice) == 0.0

    # Bob's allowance is intact
    assert tracker.get_remaining(bob) == 500.0
    can_tx_bob, _ = tracker.check_can_transact(bob, 500.0)
    assert can_tx_bob is True


def test_live_anvil_cross_chain_sync_locks_onchain_hook_and_router(anvil_url, arbitrum_like_url, tmp_path):
    """End-to-end live Anvil test:
    1. Deploy real Vault on Anvil ($500 radius).
    2. Spend $300 on Ethereum via MarketRouter -> real on-chain execution.
    3. Spend $200 on Arbitrum via MarketRouter & sync $200 to on-chain TetherGuardHook.
    4. Verify both off-chain MarketRouter AND on-chain Solidity TetherGuardHook lock at $0 remaining.
    """
    from eth_account import Account
    from tecc_brain.onchain.artifacts import Contract
    from tecc_brain.onchain.deploy import deploy_local
    from tecc_brain.onchain.executor import ChainExecutor, RecordLedger
    from tecc_brain.onchain.mandate import UserMandate, policy_hash
    from tecc_brain.onchain.rpc import Rpc
    from tecc_brain.onchain.session import provision_session_key

    rpc = Rpc(anvil_url)
    snap = rpc.call("evm_snapshot", [])
    try:
        dep = deploy_local(rpc, eth_usd=2500.0)
        key = Account.create()
        now = rpc.block_timestamp()
        mandate = UserMandate(
            account=dep.account,
            session_key=key.address,
            max_amount_usd=1000.0,
            valid_after=now - 60,
            valid_until=now + 86_400,
            risk_tier=2,
            policy=policy_hash(sorted(dep.venues)),
        )
        provision_session_key(rpc, dep, mandate)

        ledger = RecordLedger(tmp_path / "records.json")
        eth_exec = ChainExecutor(rpc, dep, key.key, mandate, ledger)
        # Arbitrum: a second, independent chain (chain id 421614) with its own vault — real transactions there too.
        arb_rpc = Rpc(arbitrum_like_url)
        arb_dep = deploy_local(arb_rpc, eth_usd=2500.0)
        arb_key = Account.create()
        arb_now = arb_rpc.block_timestamp()
        arb_mandate = UserMandate(
            account=arb_dep.account, session_key=arb_key.address, max_amount_usd=1000.0, valid_after=arb_now - 60,
            valid_until=arb_now + 86_400, risk_tier=2, policy=policy_hash(sorted(arb_dep.venues)),
        )
        provision_session_key(arb_rpc, arb_dep, arb_mandate)
        arb_exec = ArbitrumCommoditiesExecutor(arb_rpc, arb_dep, arb_mandate, session_key=arb_key.key,
                                               ledger=RecordLedger(tmp_path / "arb_records.json"))
        fisco_exec = FiscoBcosExecutor(mandate=mandate)
        tracker = CrossChainTetherTracker(daily_limit_usd=500.0)

        router = MarketRouter(
            crypto=eth_exec,
            commodities=arb_exec,
            chinese_market=fisco_exec,
            tether_tracker=tracker,
            daily_limit_usd=500.0,
        )

        # 1. Execute $300 USDC deposit into Aave on Ethereum (real on-chain tx)
        res_eth = router.submit(
            sample_intent(venue_id="aave_v3_usdc", usd=300.0, market="crypto"),
            dep.account,
        )
        assert res_eth.status == "submitted", res_eth.detail
        assert tracker.get_remaining(dep.account) == 200.0

        hook = Contract.load("TetherGuardHook", dep.hook)
        assert hook.call(rpc, "getRemainingRadius", dep.account)[0] == 200 * 10**8

        # 2. Execute $200 commodity order on Arbitrum One
        res_arb = router.submit(
            sample_intent(venue_id="paxg_hold", usd=200.0, market="commodities"),
            dep.account,
        )
        assert res_arb.status == "submitted", res_arb.detail
        assert arb_rpc.call("eth_getTransactionReceipt", [res_arb.tx_hash])["status"] == "0x1"  # real, on chain 421614
        assert tracker.get_remaining(dep.account) == 0.0

        # Sync the $200 Arbitrum spend onto the Ethereum TetherGuardHook contract
        epoch = rpc.block_timestamp() // 86400
        hook.transact(rpc, "syncCrossChainSpend", dep.account, 42161, 200 * 10**8, epoch, sender=dep.root_owner)

        # Verify on-chain cross-chain state is now $500 spent, $0 remaining
        total_spent, remaining = hook.call(rpc, "getCrossChainSpendingState", dep.account)
        assert total_spent == 500 * 10**8
        assert remaining == 0
        assert hook.call(rpc, "getRemainingRadius", dep.account)[0] == 0

        # 3. Verify MarketRouter rejects FISCO BCOS, Arbitrum, and Ethereum
        for mkt, venue in (("chinese_market", "shibor_mmf"), ("commodities", "paxg_hold"), ("crypto", "aave_v3_usdc")):
            blocked = router.submit(sample_intent(venue_id=venue, usd=10.0, market=mkt), dep.account)
            assert blocked.status == "failed"
            assert "Cross-chain tether limit exceeded" in blocked.detail

        # 4. Verify even a direct call to ChainExecutor (bypassing router) is refused ON-CHAIN by TetherGuardHook!
        direct_res = eth_exec.submit(sample_intent(venue_id="aave_v3_usdc", usd=10.0, market="crypto"), dep.account)
        assert direct_res.status == "failed"
        assert "TetherRadiusExceeded" in direct_res.detail
    finally:
        rpc.call("evm_revert", [snap])


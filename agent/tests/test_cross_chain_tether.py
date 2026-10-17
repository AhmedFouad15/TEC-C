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
    fisco_exec = FiscoBcosExecutor()
    arb_exec = ArbitrumCommoditiesExecutor()

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

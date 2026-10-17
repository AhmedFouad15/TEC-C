import pytest
from eth_account import Account

from tecc_brain.models import ActionType, CardLabel, ExecutionIntent, usd_to_onchain
from tecc_brain.onchain.artifacts import Contract
from tecc_brain.onchain.executor import (
    ArbitrumCommoditiesExecutor,
    ChainExecutor,
    CryptoExecutor,
    FiscoBcosExecutor,
    MarketRouter,
    PegGuardArbitrageExecutor,
)
from tecc_brain.onchain.mandate import UserMandate


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


def test_crypto_executor_alias():
    """CryptoExecutor must be an alias for ChainExecutor."""
    assert CryptoExecutor is ChainExecutor


def test_fisco_bcos_executor_chinese_market():
    """FiscoBcosExecutor executes on WeBank consortium chain with enterprise gas sponsorship ($0.00)."""
    mandate = UserMandate(
        account="0x" + "1" * 40,
        session_key="0x" + "2" * 40,
        max_amount_usd=1000.0,
        valid_after=0,
        valid_until=2_000_000_000,
        risk_tier=1,
        policy="0x" + "0" * 64,
    )
    executor = FiscoBcosExecutor(mandate=mandate)
    intent = sample_intent(venue_id="shibor_mmf", usd=300.0, action=ActionType.DEPOSIT, market="chinese_market")
    
    result = executor.submit(intent, "demo")
    assert result.status == "submitted"
    assert result.market == "chinese_market"
    assert result.tx_hash and result.tx_hash.startswith("0xf15c0")
    assert "WeBank" in result.detail
    assert "$0.00 gas fee" in result.detail


def test_arbitrum_commodities_executor():
    """ArbitrumCommoditiesExecutor routes commodity orders via Arbitrum One L2 rollup."""
    executor = ArbitrumCommoditiesExecutor()
    intent = sample_intent(venue_id="paxg_hold", usd=500.0, asset="USDC", action=ActionType.DEPOSIT, market="commodities")
    
    result = executor.submit(intent, "demo")
    assert result.status == "submitted"
    assert result.market == "commodities"
    assert result.tx_hash and result.tx_hash.startswith("0x42161")
    assert "Arbitrum One" in result.detail


def test_pegguard_arbitrage_executor():
    """PegGuardArbitrageExecutor blank stub pending completion of PegGuard module."""
    executor = PegGuardArbitrageExecutor()
    intent = sample_intent(venue_id="curve_steth_eth", usd=400.0, asset="ETH", action=ActionType.BUY_DISCOUNT, market="arbitrage")
    
    result = executor.submit(intent, "demo")
    assert result.status == "pending"
    assert result.market == "arbitrage"
    assert "PegGuard" in result.detail


def test_market_router_dispatch():
    """MarketRouter routes to the custom executor matching the requested market."""
    fisco = FiscoBcosExecutor()
    arb = ArbitrumCommoditiesExecutor()
    peg = PegGuardArbitrageExecutor()
    
    router = MarketRouter(chinese_market=fisco, commodities=arb, arbitrage=peg, daily_limit_usd=1000.0)
    
    # 1. Chinese Market
    intent_cn = sample_intent(market="chinese_market")
    res_cn = router.submit(intent_cn, "demo")
    assert "WeBank" in res_cn.detail

    # 2. Commodities
    intent_com = sample_intent(market="commodities")
    res_com = router.submit(intent_com, "demo")
    assert "Arbitrum One" in res_com.detail

    # 3. Arbitrage
    intent_arb = sample_intent(market="arbitrage")
    res_arb = router.submit(intent_arb, "demo")
    assert "PegGuard" in res_arb.detail


def test_crypto_execution_action_dispatch(monkeypatch):
    """Verifies that Crypto / ChainExecutor constructs calldata dispatching on exchange and action type."""
    class DummyDep:
        venues = {
            "lido_stake": "0x1111111111111111111111111111111111111111",
            "aave_v3_usdc": "0x2222222222222222222222222222222222222222",
            "curve_steth_eth": "0x3333333333333333333333333333333333333333",
        }
        usdc = "0x4444444444444444444444444444444444444444"
        eth_usd = 2500.0
        hook = "0x5555555555555555555555555555555555555555"
        validator = "0x6666666666666666666666666666666666666666"
        account = "0x7777777777777777777777777777777777777777"
        chain_id = 31337

    # Bypass Contract.load calls in __init__ for offline testing of _execution
    executor = object.__new__(ChainExecutor)
    executor.dep = DummyDep()
    executor.usdc = Contract.load("MockERC20")
    executor.protocol = Contract.load("MockDeFiProtocol")

    # 1. Staking action on Lido exchange/venue
    stake_intent = sample_intent(venue_id="lido_stake", usd=100.0, asset="ETH", action=ActionType.STAKE)
    calldata_stake = executor._execution(stake_intent)
    assert len(calldata_stake) > 0

    # 2. Swap / Buy Discount on Curve/Uniswap exchange
    swap_intent = sample_intent(venue_id="curve_steth_eth", usd=100.0, asset="USDC", action=ActionType.SWAP)
    calldata_swap = executor._execution(swap_intent)
    assert len(calldata_swap) > 0

    # 3. Deposit / Optimize Yield on Aave pool
    deposit_intent = sample_intent(venue_id="aave_v3_usdc", usd=100.0, asset="USDC", action=ActionType.DEPOSIT)
    calldata_deposit = executor._execution(deposit_intent)
    assert len(calldata_deposit) > 0

    # 4. Transfer / Withdraw
    transfer_intent = sample_intent(venue_id="aave_v3_usdc", usd=100.0, asset="USDC", action=ActionType.TRANSFER)
    calldata_transfer = executor._execution(transfer_intent)
    assert len(calldata_transfer) > 0

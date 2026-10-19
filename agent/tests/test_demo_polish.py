"""Demo polish: the off-chain leash mirrors the live vault (flags refund, passkey breakouts never count)."""

import pytest

from tecc_brain.models import ActionType, CardLabel, ExecutionIntent, usd_to_onchain
from tecc_brain.onchain.executor import ChainExecutor, CrossChainTetherTracker, MarketRouter
from tecc_brain.onchain.rpc import RpcError


class FakeVault(ChainExecutor):
    """A live vault stand-in: meters its own radius like TetherGuardHook (breakouts are sign-approved, unmetered)."""

    def __init__(self) -> None:  # no node, no contracts
        self.spent = 0.0
        self.readable = True

    def submit(self, intent, account, breakout=False):
        if not breakout:
            self.spent += intent.amount_usd
        return intent.model_copy(update={"status": "submitted", "tx_hash": "0x" + "ab" * 32})

    def spent_today_usd(self):
        if not self.readable:
            raise RpcError("node down")
        return self.spent


def order(usd):
    return ExecutionIntent(card_label=CardLabel.BEST, venue_id="aave_v3_usdc", action=ActionType.DEPOSIT,
                           asset_in="USDC", amount_usd=usd, amount_onchain=usd_to_onchain(usd))


@pytest.fixture
def vault():
    return FakeVault()


@pytest.fixture
def router(vault):
    return MarketRouter(crypto=vault, daily_limit_usd=500)


def test_a_passkey_breakout_does_not_use_up_the_daily_leash(router, vault):
    assert router.submit(order(400), "demo").status == "submitted"
    assert router.submit(order(1500), "demo", limit_usd=3000, breakout=True).status == "submitted"
    assert router.tether_tracker.get_spent("demo") == pytest.approx(400)
    after = router.submit(order(50), "demo", limit_usd=500)  # before the fix: "spent $1,900 / $500"
    assert after.status == "submitted"
    assert router.tether_tracker.get_spent("demo") == pytest.approx(450)


def test_a_flag_refunded_on_chain_frees_the_leash(router, vault):
    router.submit(order(400), "demo", limit_usd=500)
    vault.spent = 100.0  # the owner flagged a record: the vault refunded $300 of today's spend
    assert router.submit(order(300), "demo", limit_usd=400).status == "submitted"
    assert router.tether_tracker.get_spent("demo") == pytest.approx(400)


def test_the_leash_still_refuses_what_the_vault_would_refuse(router, vault):
    router.submit(order(450), "demo", limit_usd=500)
    refused = router.submit(order(100), "demo", limit_usd=500)
    assert refused.status == "failed" and "exceeds remaining allowance $50.00" in refused.detail
    assert vault.spent == pytest.approx(450)  # never sent


def test_an_unreadable_node_falls_back_to_counting_off_chain(router, vault):
    vault.readable = False
    router.submit(order(200), "demo", limit_usd=500)
    router.submit(order(900), "demo", limit_usd=2000, breakout=True)
    assert router.tether_tracker.get_spent("demo") == pytest.approx(200)


def test_breakouts_are_not_counted_on_other_markets_either():
    class Other:
        def submit(self, intent, account):
            return intent.model_copy(update={"status": "submitted", "tx_hash": "0x" + "cd" * 32})

    router = MarketRouter(crypto=Other(), daily_limit_usd=500)
    router.submit(order(100), "demo")
    router.submit(order(800), "demo", limit_usd=900, breakout=True)
    assert router.tether_tracker.get_spent("demo") == pytest.approx(100)


def test_set_market_spend_replaces_one_market_and_re_totals():
    t = CrossChainTetherTracker(daily_limit_usd=500)
    t.record_spend("demo", "commodities", 50)
    t.record_spend("demo", "crypto", 300)
    assert t.set_market_spend("demo", "crypto", 120) == pytest.approx(170)
    assert t.get_spent("demo") == pytest.approx(170)
    with pytest.raises(ValueError):
        t.set_market_spend("demo", "crypto", float("nan"))

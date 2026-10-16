import pytest

from tecc_brain.intent.sieve import mask, mask_payload, restore

ADDR = "0x" + "c0ffee" * 6 + "abcd"
DID = "did:weid:101:0x" + "12" * 20


def test_amounts_are_masked_but_assets_and_verbs_stay():
    masked, vault = mask("Stake my 10 ETH")
    assert masked == "Stake my <AMT_1> ETH"
    assert vault == {"<AMT_1>": "10"}


def test_dollar_sign_is_kept_so_the_currency_stays_readable():
    masked, _ = mask("Optimize my $1,500 USDC")
    assert masked == "Optimize my $<AMT_1> USDC"


def test_addresses_dids_ens_and_emails_never_leave_the_machine():
    text = f"Owner {DID} with wallet {ADDR} (alice.eth, alice@example.com) holds 25,000 USDC"
    masked, _ = mask(text)
    for secret in (DID, ADDR, "alice.eth", "alice@example.com", "25,000"):
        assert secret not in masked


def test_same_value_gets_the_same_token():
    masked, vault = mask("move 500 then another 500")
    assert masked == "move <AMT_1> then another <AMT_1>"
    assert len(vault) == 1


def test_tokens_are_not_re_masked():
    masked, vault = mask(f"{ADDR} 1 2 3 4 5 6 7 8 9 10 11")
    assert "<ADDR_1>" in masked and "<AMT_11>" in masked
    assert restore(masked, vault) == f"{ADDR} 1 2 3 4 5 6 7 8 9 10 11"


@pytest.mark.parametrize(
    "text",
    ["Stake my 10 ETH", "Optimize my $1,500 USDC portfolio", f"pay 1.5k to {ADDR} for {DID}", "no numbers here"],
)
def test_restore_round_trips(text):
    masked, vault = mask(text)
    assert restore(masked, vault) == text


def test_payload_balances_and_addresses_are_masked_recursively():
    payload = {"account": ADDR, "nav_usd": 26500, "positions": [{"asset": "USDC", "amount_usd": 1500}], "tier": 2}
    masked, vault = mask_payload(payload)
    assert masked["account"].startswith("<ADDR_")
    assert masked["nav_usd"].startswith("<AMT_") and masked["positions"][0]["amount_usd"].startswith("<AMT_")
    assert masked["positions"][0]["asset"] == "USDC" and masked["tier"] == 2
    assert ADDR in vault.values()

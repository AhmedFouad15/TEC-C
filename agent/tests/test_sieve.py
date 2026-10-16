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


@pytest.mark.parametrize("text, secret", [
    ("Stake my 10ETH", "10"), ("move USDC1500 now", "1500"), ("$1500usdc please", "1500"),
    ("tx 0x" + "ab" * 32, "ab" * 32), ("send to 0X" + "AB" * 20, "AB" * 20),
    ("to 0x" + " ".join(["abab"] * 10), "abab abab"),
    ("btc bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq", "bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq"),
])
def test_glued_numbers_and_other_address_formats_are_masked(text, secret):
    masked, vault = mask(text)
    assert secret not in masked
    assert restore(masked, vault) == text


def test_payload_numbers_under_any_key_are_masked_except_structural_ones():
    payload = {"balances": {"USDC": 1500, ADDR: 7}, "tier": 2, "horizon_days": 365, "qty": 3}
    masked, vault = mask_payload(payload)
    flat = repr(masked)
    for secret in ("1500", ADDR, "'qty': 3"):
        assert secret not in flat
    assert masked["tier"] == 2 and masked["horizon_days"] == 365

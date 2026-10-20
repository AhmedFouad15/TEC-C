"""Coverage: core math, reference data, onboarding (every possible quiz answer), the cross-chain tether tracker,
P-256 passkey crypto, WebAuthn helpers and the PegGuard 25-asset catalog."""

import hashlib
import itertools

import pytest

from tecc_brain.biometrics.passkey import (
    P256_N,
    DecentralizedBiometricManager,
    build_authenticator_data,
    generate_p256_keypair,
    is_canonical_low_s,
    is_on_p256_curve,
    normalize_low_s,
    parse_authenticator_data,
    sign_webauthn_p256,
    verify_p256_digest,
)
from tecc_brain.learning.onboarding import QUIZ, TIER_POINTS, onboard, score_quiz
from tecc_brain.learning.store import account_key
from tecc_brain.models import LAMBDA_BANDS, RiskTier, onchain_to_usd, usd_to_onchain
from tecc_brain.onchain.executor import CrossChainTetherTracker
from tecc_brain.pegguard.engine import (
    DEFAULT_CONTAGION_MATRIX,
    PEGGUARD_ASSET_CATALOG,
    default_pegguard_input_for_symbol,
    resolve_canonical_symbol,
)
from tecc_brain.reference import load_reference
from tecc_brain.virtual_session.webauthn_engine import b64url_decode, b64url_encode, compute_action_hash

REF = load_reference()
P256_HALF = P256_N // 2

# --- 8-decimal on-chain USD -----------------------------------------------------------------------------------------

USD_VALUES = [0.0, 0.01, 0.1, 0.5, 1.0, 1.25, 2.5, 9.99, 10.0, 33.33, 99.99, 100.0, 250.0, 400.0, 499.99, 500.0,
              1000.0, 1234.56, 2500.0, 9999.99, 10_000.0, 25_000.0, 100_000.0, 123_456.78, 1_000_000.0, 0.00000001,
              0.12345678, 42.42424242, 7.5, 3.14159265]


@pytest.mark.parametrize("usd", USD_VALUES)
def test_usd_round_trips_through_the_on_chain_unit(usd):
    assert onchain_to_usd(usd_to_onchain(usd)) == pytest.approx(usd, abs=1e-8)


@pytest.mark.parametrize("usd", USD_VALUES)
def test_on_chain_usd_is_an_integer_with_eight_decimals(usd):
    value = usd_to_onchain(usd)
    assert isinstance(value, int)
    assert value == round(usd * 10**8)


# --- risk tiers ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("tier", list(RiskTier))
def test_each_tier_has_a_valid_loss_aversion_band(tier):
    lo, hi = LAMBDA_BANDS[tier]
    assert 0 <= lo < hi


def test_tiers_match_the_hook_constants():
    assert [int(t) for t in RiskTier] == [1, 2, 3]


# --- reference data ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("venue_id", sorted(REF.venues))
def test_every_venue_accepts_only_known_assets(venue_id):
    venue = REF.venues[venue_id]
    assert venue.accepts and set(venue.accepts) <= set(REF.assets)


@pytest.mark.parametrize("venue_id", sorted(REF.venues))
def test_every_venue_has_a_hook_risk_tier(venue_id):
    assert int(REF.venues[venue_id].tier) in (1, 2, 3)


@pytest.mark.parametrize("venue_id", sorted(REF.venues))
def test_every_venue_belongs_to_a_market(venue_id):
    venue = REF.venues[venue_id]
    assert venue.market in ("crypto", "chinese_market", "commodities")
    assert venue.protocol and venue.id == venue_id


@pytest.mark.parametrize("symbol", sorted(REF.assets))
def test_every_asset_is_keyed_by_its_symbol(symbol):
    asset = REF.assets[symbol]
    assert asset.symbol == symbol
    assert asset.peg in (None, "USD", "ETH", "XAU")


# --- onboarding: every possible answer set --------------------------------------------------------------------------------

ALL_ANSWERS = [dict(zip([q.id for q in QUIZ], combo)) for combo in itertools.product(*[[o.id for o in q.options] for q in QUIZ])]


def _points(answers):
    return sum(next(o.points for o in q.options if o.id == answers[q.id]) for q in QUIZ)


@pytest.mark.parametrize("answers", ALL_ANSWERS, ids=lambda a: "-".join(a.values()))
def test_every_quiz_answer_set_scores_to_a_consistent_profile(answers):
    result = score_quiz(answers)
    assert result.points == _points(answers)
    lo, hi = TIER_POINTS[result.tier]
    if answers["horizon"] == "soon" and result.points >= TIER_POINTS[RiskTier.AGGRESSIVE][0]:
        assert result.tier == RiskTier.BALANCED  # money needed soon caps the tier
    else:
        assert lo <= result.points <= hi
    band_lo, band_hi = LAMBDA_BANDS[result.tier]
    assert band_lo <= result.lam <= band_hi
    assert result.rationale


@pytest.mark.parametrize("answers", ALL_ANSWERS[::9], ids=lambda a: "-".join(a.values()))
def test_onboarding_builds_the_profile_the_quiz_scored(answers):
    result = score_quiz(answers)
    profile = onboard("quiz-user", answers)
    assert profile.tier == result.tier and profile.lam == pytest.approx(result.lam)


# --- account names ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("account,key", [
    ("demo", "demo"), ("Demo", "demo"), ("alice_01", "alice_01"), ("team-lead", "team-lead"),
    ("0x" + "AB" * 20, "0x" + "ab" * 20), ("a" * 64, "a" * 64), ("judge", "judge"), ("X", "x"),
])
def test_valid_account_names_are_normalised(account, key):
    assert account_key(account) == key


# --- cross-chain tether tracker ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("spends,limit", [
    ([100.0], 500.0), ([100.0, 200.0], 500.0), ([499.99], 500.0), ([250.0, 250.0], 500.0),
    ([10.0] * 10, 1000.0), ([0.01, 0.02, 0.03], 1.0), ([1000.0, 1500.0], 2500.0), ([75.5, 24.5], 100.0),
])
def test_tracker_totals_spend_and_reports_what_is_left(spends, limit):
    tracker = CrossChainTetherTracker(daily_limit_usd=limit)
    for i, amount in enumerate(spends):
        assert tracker.check_can_transact("acct", amount, limit)[0]
        tracker.record_spend("acct", ["crypto", "commodities", "chinese_market"][i % 3], amount)
    assert tracker.get_spent("acct") == pytest.approx(sum(spends))
    assert tracker.get_remaining("acct", limit) == pytest.approx(limit - sum(spends))


@pytest.mark.parametrize("market", ["crypto", "commodities", "chinese_market", "arbitrage"])
def test_tracker_aggregates_across_markets(market):
    tracker = CrossChainTetherTracker(daily_limit_usd=500)
    tracker.record_spend("acct", "crypto", 300)
    tracker.record_spend("acct", market, 100)
    assert tracker.get_spent("acct") == pytest.approx(400)
    assert tracker.check_can_transact("acct", 100, 500)[0]


def test_tracker_accounts_are_independent():
    tracker = CrossChainTetherTracker(daily_limit_usd=500)
    tracker.record_spend("a", "crypto", 400)
    assert tracker.get_spent("b") == 0
    assert tracker.check_can_transact("b", 500, 500)[0]


def test_tracker_epochs_are_independent():
    tracker = CrossChainTetherTracker(daily_limit_usd=500)
    tracker.record_spend("a", "crypto", 400, epoch=1)
    assert tracker.get_spent("a", epoch=2) == 0


def test_tracker_reset_clears_the_epoch():
    tracker = CrossChainTetherTracker(daily_limit_usd=500)
    tracker.record_spend("a", "crypto", 400)
    tracker.reset_epoch("a")
    assert tracker.get_spent("a") == 0


# --- P-256 passkeys --------------------------------------------------------------------------------------------------------

SEEDS = list(range(1, 26))


@pytest.mark.parametrize("seed", SEEDS)
def test_generated_passkeys_lie_on_the_p256_curve(seed):
    _, qx, qy = generate_p256_keypair(seed_int=seed)
    assert is_on_p256_curve(qx, qy)


@pytest.mark.parametrize("seed", SEEDS)
def test_webauthn_signatures_verify_with_the_signers_key(seed):
    key, qx, qy = generate_p256_keypair(seed_int=seed)
    auth = build_authenticator_data(sign_count=seed)
    challenge = hashlib.sha256(f"challenge-{seed}".encode()).digest()
    r, s, digest = sign_webauthn_p256(key, auth, challenge)
    assert digest == hashlib.sha256(auth + challenge).digest()
    assert is_canonical_low_s(r, s)
    assert verify_p256_digest(digest, r, s, qx, qy)


@pytest.mark.parametrize("seed", SEEDS)
def test_a_signature_does_not_verify_for_another_message(seed):
    key, qx, qy = generate_p256_keypair(seed_int=seed)
    auth = build_authenticator_data()
    r, s, _ = sign_webauthn_p256(key, auth, hashlib.sha256(b"original").digest())
    assert not verify_p256_digest(hashlib.sha256(b"tampered").digest(), r, s, qx, qy)


@pytest.mark.parametrize("s", [1, 2, 12345, P256_HALF - 1, P256_HALF, P256_HALF + 1, P256_N - 2, P256_N - 1])
def test_low_s_normalisation(s):
    low = normalize_low_s(s)
    assert 0 < low <= P256_HALF
    assert low in (s, P256_N - s)


@pytest.mark.parametrize("up,uv", [(True, True), (True, False), (False, True), (False, False)])
@pytest.mark.parametrize("count", [0, 1, 7, 65535, 2**32 - 1])
def test_authenticator_data_flags_and_counter_round_trip(up, uv, count):
    parsed = parse_authenticator_data(build_authenticator_data(rp_id="localhost", user_present=up,
                                                               user_verified=uv, sign_count=count))
    assert (parsed.user_present_up, parsed.user_verified_uv, parsed.sign_count) == (up, uv, count)
    assert parsed.rp_id_hash_hex == "0x" + hashlib.sha256(b"localhost").hexdigest()


@pytest.mark.parametrize("seed", SEEDS[:10])
def test_a_registered_passkey_opens_the_biometric_window(seed):
    mgr = DecentralizedBiometricManager()
    key, qx, qy = generate_p256_keypair(seed_int=seed)
    mgr.register_passkey(f"acct{seed}", qx, qy, key_id="primary")
    auth = build_authenticator_data(user_present=True, user_verified=True, sign_count=1)
    challenge = hashlib.sha256(f"open-{seed}".encode()).digest()
    r, s, _ = sign_webauthn_p256(key, auth, challenge)
    result = mgr.verify_webauthn_assertion(f"acct{seed}", auth, challenge, r, s, qx, qy, require_uv=True)
    assert result.verified and result.key_id == "primary"
    assert mgr.is_biometric_window_active(f"acct{seed}")[0]


@pytest.mark.parametrize("devices", [1, 2, 3, 5])
def test_several_devices_can_be_registered(devices):
    mgr = DecentralizedBiometricManager()
    for i in range(devices):
        _, qx, qy = generate_p256_keypair(seed_int=100 + i)
        mgr.register_passkey("multi", qx, qy, key_id=f"device-{i}", device_label=f"Device {i}")
    keys = mgr.get_passkeys("multi")
    assert len(keys) == devices
    assert sum(k.is_primary for k in keys) >= 1


# --- WebAuthn helpers ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("length", [0, 1, 2, 3, 4, 5, 16, 31, 32, 33, 37, 64, 65, 100, 255])
def test_b64url_round_trips(length):
    data = bytes((i * 7 + 3) % 256 for i in range(length))
    encoded = b64url_encode(data)
    assert "=" not in encoded and "+" not in encoded and "/" not in encoded
    assert b64url_decode(encoded) == data


@pytest.mark.parametrize("action", ["execute", "arbitrage/toggle", "withdraw", "approve"])
def test_action_hash_is_deterministic_and_order_independent(action):
    a = compute_action_hash(action, {"proposal_id": "p1", "label": "BEST"})
    b = compute_action_hash(f"  {action.upper()} ", {"label": "BEST", "proposal_id": "p1"})
    assert a == b and len(a) == 32


@pytest.mark.parametrize("params", [{"proposal_id": "p1"}, {"proposal_id": "p2"}, {"amount": 1}, {"amount": 2}])
def test_action_hash_binds_the_parameters(params):
    assert compute_action_hash("execute", params) != compute_action_hash("execute", {**params, "extra": True})


# --- PegGuard catalog ------------------------------------------------------------------------------------------------------

CATALOG = sorted(PEGGUARD_ASSET_CATALOG)


def test_the_catalog_has_25_assets():
    assert len(CATALOG) == 25


@pytest.mark.parametrize("symbol", CATALOG)
def test_every_catalog_asset_is_fully_specified(symbol):
    spec = PEGGUARD_ASSET_CATALOG[symbol]
    assert spec.symbol == symbol and spec.name
    assert spec.p_par > 0 and spec.r_fee >= 0 and spec.tau_redeem_days >= 0
    assert spec.anchor_asset in ("USD", "EUR", "ETH", "BTC", "XAU")
    assert spec.peg_mechanism and spec.primary_long_venue and spec.primary_short_venue


@pytest.mark.parametrize("symbol", CATALOG)
def test_every_catalog_asset_trades_somewhere(symbol):
    spec = PEGGUARD_ASSET_CATALOG[symbol]
    assert spec.ethereum_l1_venues or spec.arbitrum_l2_venues


@pytest.mark.parametrize("symbol", CATALOG)
def test_symbols_resolve_case_insensitively(symbol):
    assert resolve_canonical_symbol(symbol.lower()) == symbol
    assert resolve_canonical_symbol(f"  {symbol.upper()} ") == symbol


@pytest.mark.parametrize("symbol", CATALOG)
def test_a_default_scan_input_exists_for_every_asset(symbol):
    inp = default_pegguard_input_for_symbol(symbol, order_size_usd=250.0)
    assert inp.symbol == symbol
    assert inp.layer1.p_par == pytest.approx(PEGGUARD_ASSET_CATALOG[symbol].p_par)
    assert inp.layer5.base_size_usd == 250.0


@pytest.mark.parametrize("source", sorted(DEFAULT_CONTAGION_MATRIX))
def test_contagion_betas_are_bounded(source):
    for target, beta in DEFAULT_CONTAGION_MATRIX[source].items():
        assert -1.0 <= beta <= 1.0 and target != source

"""Formal verification test suite for Fail-Closed Strictness Hierarchy (Math > AI)
and Privacy-Preserving On-Chain Audit Anchors.

Addresses requirements for:
1. Tsinghua Academic Panel (Prof. Dacheng Xiu & Prof. Wolfgang Härdle):
   - Asymmetric Risk Bounding (B_{AI} ⊆ B_{math}): AI can only tighten constraints, never loosen.
   - Deterministic Governance: Mathematical Layer 1-5 rejection cannot be overridden by AI/sentiment optimism.
   - Fail-Closed Resilience: Latency/Timeout (> 8.0s) fails closed into deterministic HOLD/rules baseline.
2. WeBank Strategic Agenda:
   - Zero-knowledge regulatory compliance via SHA-256 on-chain audit anchors on FISCO BCOS.
"""

from datetime import datetime, timezone
import json
import time
import pytest

from tecc_brain.graph.brain import (
    BRAIN_TIMEOUT_S,
    BrainReport,
    BrainVerdict,
    apply_verdict,
    synthesize,
    validate_verdict,
)
from tecc_brain.models import (
    ActionType,
    AutonomyMode,
    Card,
    CardLabel,
    Candidate,
    Decision,
    FeedbackEvent,
    Mandate,
    RiskTier,
    Signal,
)
from tecc_brain.onchain.audit_anchor import (
    AuditRecordType,
    compute_audit_record_hash,
)
from tecc_brain.pegguard import (
    PegGuardEngine,
    PegGuardMarketInput,
    default_pegguard_input_for_symbol,
)
from tecc_brain.learning.update import learn, new_profile


@pytest.fixture
def mock_brain_payload():
    return {
        "schema_version": "tecc.brain_report.v1",
        "request_id": "req-strictness-001",
        "mandate": {"action": "deposit", "amount_usd": 500.0},
        "candidates": [
            {
                "id": "c0",
                "venue_id": "aave_v3_usdc",
                "max_amount_usd": 500.0,
                "amount_usd": 500.0,
                "allowed_mode": "PROPOSE",  # Rule layer restricted to PROPOSE
                "label": "BETTER",
                "exposed_to": [],
            }
        ],
        "limits": {
            "baseline_auto_usd": 0.0,
            "vault_radius_remaining_usd": 500.0,
            "soft_limit_usd": 500.0,
        },
        "vetoes": [{"id": "veto_curve", "venue_id": "curve_3pool"}],
        "regimes": {
            "USDC": {"p_failure": 0.05},
        },
    }


def _make_candidate(cand_id: int, venue_id: str = "aave_v3_usdc", amount: float = 500.0, mode: AutonomyMode = AutonomyMode.AUTO) -> Candidate:
    return Candidate(
        venue_id=venue_id,
        action=ActionType.DEPOSIT,
        asset_in="USDC",
        amount_usd=amount,
        apy=0.05,
    )


def _make_test_decision(card_mode: AutonomyMode = AutonomyMode.PROPOSE, amount: float = 500.0) -> Decision:
    cand = _make_candidate(0, amount=amount, mode=card_mode)
    card = Card(
        label=CardLabel.BETTER,
        candidate=cand,
        mode=card_mode,
        headline="Test Candidate",
    )
    return Decision(
        mandate=Mandate(raw_text=f"deposit {amount} USDC", action=ActionType.DEPOSIT, kind="deposit", asset="USDC", amount=amount, amount_usd=amount),
        mode=card_mode,
        auto_amount_usd=amount if card_mode == AutonomyMode.AUTO else 0.0,
        proposed_amount_usd=0.0 if card_mode == AutonomyMode.AUTO else amount,
        cards=[card],
    )


# =============================================================================
# 1. Asymmetric Bounding Tests (B_{AI} ⊆ B_{math})
# =============================================================================

def test_ai_cannot_loosen_mode_from_propose_to_auto(mock_brain_payload):
    """Verify that if mathematical/rule layers classify a candidate as PROPOSE,
    an LLM reply attempting to upgrade it to AUTO is strictly rejected by the validator."""
    payload = mock_brain_payload

    # Malicious or hallucinated LLM reply attempting to upgrade to AUTO
    bad_reply = json.dumps({
        "schema_version": "tecc.brain_report.v1",
        "request_id": payload["request_id"],
        "decision": "EXECUTE",
        "allocations": [{"candidate_id": "c0", "amount_usd": 500.0, "mode": "AUTO"}],
        "total_auto_usd": 500.0,
        "reason_codes": ["TOP_SCORE"],
        "vetoes_honored": ["veto_curve"],
        "signal_conflicts": ["NONE"],
        "confidence": 0.99,
        "user_explanation": "Attempting to force auto execution.",
    })

    verdict, reason = validate_verdict(bad_reply, payload)
    assert verdict is None
    assert reason is not None
    assert "looser than allowed" in reason or "more autonomy than the gatekeeper allows" in reason


def test_ai_cannot_allocate_to_vetoed_venue(mock_brain_payload):
    """Verify that an LLM cannot allocate funds to a mathematically vetoed venue."""
    payload = dict(mock_brain_payload)
    payload["candidates"] = [
        {
            "id": "c0",
            "venue_id": "curve_3pool",  # matches vetoed venue
            "max_amount_usd": 500.0,
            "amount_usd": 500.0,
            "allowed_mode": "PROPOSE",
            "label": "GOOD",
            "exposed_to": [],
        }
    ]

    bad_reply = json.dumps({
        "schema_version": "tecc.brain_report.v1",
        "request_id": payload["request_id"],
        "decision": "PROPOSE",
        "allocations": [{"candidate_id": "c0", "amount_usd": 500.0, "mode": "PROPOSE"}],
        "total_auto_usd": 0.0,
        "reason_codes": ["TOP_SCORE"],
        "vetoes_honored": ["veto_curve"],
        "signal_conflicts": ["NONE"],
        "confidence": 0.90,
        "user_explanation": "Allocating to vetoed Curve.",
    })

    verdict, reason = validate_verdict(bad_reply, payload)
    assert verdict is None
    assert "vetoed venue" in reason


def test_ai_cannot_exceed_mathematical_auto_budget(mock_brain_payload):
    """Verify that total_auto_usd can never exceed baseline_auto_usd established by math."""
    payload = dict(mock_brain_payload)
    payload["candidates"][0]["allowed_mode"] = "AUTO"
    payload["limits"]["baseline_auto_usd"] = 200.0
    payload["candidates"][0]["max_amount_usd"] = 200.0

    bad_reply = json.dumps({
        "schema_version": "tecc.brain_report.v1",
        "request_id": payload["request_id"],
        "decision": "EXECUTE",
        "allocations": [{"candidate_id": "c0", "amount_usd": 500.0, "mode": "AUTO"}],
        "total_auto_usd": 500.0,
        "reason_codes": ["TOP_SCORE"],
        "vetoes_honored": ["veto_curve"],
        "signal_conflicts": ["NONE"],
        "confidence": 0.95,
        "user_explanation": "Attempting to exceed baseline auto limit.",
    })

    verdict, reason = validate_verdict(bad_reply, payload)
    assert verdict is None
    assert reason is not None
    assert "amount above its cap" in reason or "more autonomy than the gatekeeper allows" in reason


def test_ai_can_tighten_or_veto_approved_candidates(mock_brain_payload):
    """Verify that the AI can validly tighten AUTO down to PROPOSE."""
    payload = dict(mock_brain_payload)
    payload["candidates"][0]["allowed_mode"] = "AUTO"
    payload["limits"]["baseline_auto_usd"] = 200.0
    payload["candidates"][0]["max_amount_usd"] = 200.0

    decision = _make_test_decision(card_mode=AutonomyMode.AUTO, amount=200.0)

    valid_tighten_reply = json.dumps({
        "schema_version": "tecc.brain_report.v1",
        "request_id": payload["request_id"],
        "decision": "PROPOSE",
        "allocations": [{"candidate_id": "c0", "amount_usd": 200.0, "mode": "PROPOSE"}],
        "total_auto_usd": 0.0,
        "reason_codes": ["LOW_CONFIDENCE"],
        "vetoes_honored": ["veto_curve"],
        "signal_conflicts": ["NONE"],
        "confidence": 0.50,
        "user_explanation": "Downgrading to propose due to market volatility.",
    })

    verdict, reason = validate_verdict(valid_tighten_reply, payload)
    assert verdict is not None
    assert reason is None

    final_decision = apply_verdict(decision, verdict)
    assert final_decision.cards[0].mode == AutonomyMode.PROPOSE
    assert final_decision.auto_amount_usd == 0.0


# =============================================================================
# 2. Deterministic Governance Tests (Math Layer 1-5 > Probabilistic AI)
# =============================================================================

def test_mathematical_layer1_rejection_cannot_be_overridden_by_ai():
    """Verify that when an asset's spread is not below Baseline*(t) (delta >= 0),
    the trade is rejected even if Layer 4 NLP/AI score is 1.0 (maximum bullish)."""
    engine = PegGuardEngine()
    inp = default_pegguard_input_for_symbol("USDC", order_size_usd=1000.0, current_ratio=1.000)
    inp = inp.model_copy(update={
        "layer4": inp.layer4.model_copy(update={
            "p_insolvency_finbert": 0.0,
            "microstructure_inflow_ratio": 1.0,
            "retail_fomo_score": 1.0,
        }),
    })

    decision = engine.evaluate(inp)
    assert not decision.authorized
    assert any("Layer 1" in r for r in decision.rejection_reasons)


def test_mathematical_layer2_death_spiral_rejects_regardless_of_ai():
    """Verify that when non-stationary divergence (beta >= 1.0 or death spiral) is detected,
    AI optimism cannot authorize execution."""
    engine = PegGuardEngine()
    inp = default_pegguard_input_for_symbol("USDC", order_size_usd=1000.0, current_ratio=0.980)
    inp = inp.model_copy(update={
        "spread_series": [0.010, 0.015, 0.022, 0.035, 0.055, 0.080],
        "layer4": inp.layer4.model_copy(update={
            "p_insolvency_finbert": 0.0,
            "microstructure_inflow_ratio": 1.0,
        }),
    })

    decision = engine.evaluate(inp)
    assert not decision.authorized
    assert any("Layer 2" in r or "Regime" in r for r in decision.rejection_reasons)


# =============================================================================
# 3. Fail-Closed Resilience on Timeout (> 8.0s)
# =============================================================================

def test_ai_timeout_fails_closed_to_rules_baseline(mock_brain_payload):
    """Verify that when the LLM synthesis call times out (> 8.0s),
    the system fails closed to the conservative rule-based baseline without crashing."""
    payload = mock_brain_payload
    decision = _make_test_decision(card_mode=AutonomyMode.AUTO, amount=200.0)

    def slow_llm(sys_prompt: str, user_payload: str) -> str:
        time.sleep(0.5)
        return "{}"

    final_decision, report = synthesize(decision, payload, slow_llm, timeout_s=0.05)
    assert report.producer == "rules"
    assert report.fallback_reason is not None
    assert "TimeoutError" in report.fallback_reason or "failed" in report.fallback_reason


# =============================================================================
# 4. Privacy-Preserving On-Chain Audit Anchors
# =============================================================================

def test_deterministic_audit_record_hash_computation():
    """Verify that RecordHash = SHA256(account || symbol || action || P_cons || timestamp || salt)
    is strictly deterministic and formatted as 0x-prefixed 32-byte hex."""
    h1 = compute_audit_record_hash(
        account="0x1111111111111111111111111111111111111111",
        symbol="USDC",
        action="ARBITRAGE_EXECUTED",
        p_cons=0.9850,
        timestamp=1700000000,
        salt="curve_3pool",
    )
    h2 = compute_audit_record_hash(
        account="0x1111111111111111111111111111111111111111",
        symbol="USDC",
        action="ARBITRAGE_EXECUTED",
        p_cons=0.9850,
        timestamp=1700000000,
        salt="curve_3pool",
    )
    assert h1 == h2
    assert h1.startswith("0x")
    assert len(bytes.fromhex(h1[2:])) == 32


def test_learning_update_populates_audit_record_hash():
    """Verify that feedback events automatically get an audit_record_hash when learned."""
    profile = new_profile("0xAlice", RiskTier.CONSERVATIVE)
    event = FeedbackEvent(
        event_id="ev_001",
        signal=Signal.NOTE_PENALTY,
        venue_id="aave_v3_usdc",
        amount_usd=250.0,
        at=datetime.now(timezone.utc),
        note="Too risky, avoid Aave for now",
    )
    assert event.audit_record_hash is None

    res = learn(profile, event)
    assert res.applied
    recorded_event = res.profile.history[-1]
    assert recorded_event.audit_record_hash is not None
    assert recorded_event.audit_record_hash.startswith("0x")
    assert len(bytes.fromhex(recorded_event.audit_record_hash[2:])) == 32

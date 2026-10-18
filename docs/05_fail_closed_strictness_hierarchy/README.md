# Tec-C: Fail-Closed Strictness Hierarchy (Math > AI)

> **Academic Foundation**: Formulated for the Tsinghua University PBCSF Academic Evaluation Panel  
> **Theoretical Guidance**: Prof. Dacheng Xiu (Econometrics & Machine Learning) & Prof. Wolfgang Härdle (Quantitative Finance)  
> **Core Principle**: **Mathematical Invariants Strictly Govern Probabilistic AI**

---

## 1. The Core Problem: Probabilistic Fragility vs Enterprise Safety

Large Language Models (LLMs) and sentiment algorithms possess significant reasoning and synthesis capabilities, but suffer from three fatal flaws during market panics and high-volatility flash crashes:
1. **Hallucination & Non-Determinism**: A model may recommend high-risk actions under subtle prompt perturbations.
2. **Inference Latency & Timeouts**: In an acute liquidity drain, API lag or cloud outages can delay risk responses.
3. **Prompt Injection & Adversarial Payloads**: Malicious calldata or poisoned news headlines could manipulate an unconstrained model into authorizing unauthorized transactions.

The Tsinghua academic panel demands that autonomous financial agents **never delegate ultimate solvency, liquidity, or compliance checks to a probabilistic model**.

---

## 2. The Strict Hierarchy: Layered Invariants

Tec-C enforces an absolute, unidirectional hierarchy:

$$\text{Smart Contract Invariants (EIP-7579)} \succ \text{Econometric Proofs (Sharpe/CVaR/Markov)} \succ \text{AI LLM Synthesis}$$

```
┌────────────────────────────────────────────────────────────────────────┐
│  Level 1: Smart Contract Cryptographic Hooks (Unbreakable)             │
│  - Tether Radius daily spending cap                                    │
│  - Whitelisted module targets & authorized ERC-20 tokens               │
│  - Biometric WebAuthn FaceID proof required for limit breakout        │
│  - Deadman switch heartbeat timer                                      │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │
┌────────────────────────────────────────────────────────────────────────┐
│  Level 2: Econometric & Quantitative Liquidity Filters                 │
│  - Layer 1: Dual-anchor fair value calibration (FV_fund, R_cons)       │
│  - Layer 2: 3-regime Markov-switching recovery probability (P_rec)     │
│  - Layer 3: Recovery-risk adjusted expected value (EV >= +15 bps)      │
│  - Layer 4: Hard token health & contagion veto                         │
│  - Layer 5: Contagion brake position sizing cap (Q*)                   │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │
┌────────────────────────────────────────────────────────────────────────┐
│  Level 3: Probabilistic AI Brain (Asymmetric Restriction Only)         │
│  - Single-pass JSON verdict synthesis                                 │
│  - Can strictly TIGHTEN constraints (size down, veto, hold)            │
│  - CANNOT expand autonomy, add venues, or override Level 1–2 vetoes   │
│  - Times out into Fail-Closed HOLD state after 8.0 seconds             │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Mathematical Proof of Asymmetric Bounding

Let $\mathcal{C}_{math}$ denote the set of candidate allocations approved by the deterministic econometric engine, with maximum permissible capital allocation $Q^*_{math}$:

$$\mathcal{C}_{math} = \left\{ c \in \mathcal{V} \;\middle|\; \text{Tier}(c) \le \text{Tier}_{user}, \; \text{CVaR}_{95}(c) \le \gamma, \; P_{\text{failure}}(c) < 0.30 \right\}$$

The AI Brain produces an allocation proposal $\mathcal{C}_{AI}$ with capital $Q_{AI}$. The system enforces the **Strict Sub-Set and Monotonicity Invariants**:

### Invariant 1 (Candidate Set Contraction)
$$\mathcal{C}_{\text{final}} \subseteq \mathcal{C}_{math}$$
*The AI cannot introduce a venue, asset, or recipient that was not already approved by Level 1 and Level 2.*

### Invariant 2 (Monotonic Capital Cap)
$$0 \le Q^*_{\text{final}} \le \min\left(Q^*_{math}, \; Q_{AI}, \; \text{TetherRadius}_{\text{remaining}}\right)$$
*The AI can reduce the order size (e.g. from $1,000 to $500 due to ambiguous news sentiment), but can NEVER increase allocation above the quantitative maximum.*

### Invariant 3 (Unidirectional Autonomy Progression)
$$\text{Strictness}(m_{\text{final}}) \ge \text{Strictness}(m_{\text{baseline}})$$
$$\text{AUTO (0)} \longrightarrow \text{PROPOSE (1)} \longrightarrow \text{BREAKOUT (2)} \longrightarrow \text{BLOCKED (3)}$$
*The AI can move a proposed action to the right (e.g. requiring human FaceID approval), but can NEVER downgrade a `PROPOSE` or `BLOCKED` decision to `AUTO`.*

---

## 4. Fail-Closed Timeout & Adversarial Isolation

### A. Pre-LLM Regex Firewall & Privacy Sieve
Untrusted user text is scanned by [`agent/tecc_brain/intent/firewall.py`](..\../agent/tecc_brain/intent/firewall.py) for prompt injections, delimiter attacks, and role hijacking **before** any model is invoked. If an attack is suspected:
- The input is immediately rejected with status `refused`.
- The LLM is never called, saving compute and preventing prompt leakage.

### B. Fail-Closed 8-Second Circuit Breaker
If the external LLM or sentiment API lags or times out ($t > 8.0\text{ seconds}$):
- The model synthesis is immediately abandoned.
- The system executes `report_from_decision()`: reverting to the conservative rule-based baseline or safe `HOLD` state.
- A fallback reason is logged to the immutable audit report.

---

## 5. Formal Verification Test Suite

Tec-C's fail-closed hierarchy is verified by dedicated automated tests in [`agent/tests/test_strictness_hierarchy.py`](..\../agent/tests/test_strictness_hierarchy.py):

| Test Case | Invariant Verified | Result |
|---|---|---|
| `test_ai_cannot_loosen_mode_from_propose_to_auto` | Invariant 3: Upgrade from PROPOSE to AUTO strictly rejected | ✅ Passed |
| `test_ai_cannot_allocate_to_vetoed_venue` | Invariant 1: Allocation to mathematically vetoed venue rejected | ✅ Passed |
| `test_ai_cannot_exceed_mathematical_auto_budget` | Invariant 2: $Q^*_{\text{final}} \le Q^*_{math}$ enforced | ✅ Passed |
| `test_ai_can_tighten_or_veto_approved_candidates` | Asymmetric tightening: AI can safely step down AUTO to PROPOSE | ✅ Passed |
| `test_mathematical_layer1_rejection_cannot_be_overridden_by_ai` | Deterministic Governance: Layer 1 $\Delta \ge 0$ rejects even if AI optimism = 1.0 | ✅ Passed |
| `test_mathematical_layer2_death_spiral_rejects_regardless_of_ai` | Deterministic Governance: Non-stationary divergence rejects regardless of AI | ✅ Passed |
| `test_ai_timeout_fails_closed_to_rules_baseline` | Fail-Closed Resilience: Timeout fails closed into conservative baseline | ✅ Passed |


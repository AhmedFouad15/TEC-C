# Part 5: Mathematical Invariant Proofs (Math > AI Hierarchy)

> **Prepared for**: Academic Reviewers (Tsinghua University PBCSF)  
> **Topic**: Deterministic Governance of Autonomous Financial Agents

---

## 1. Mathematical Formalism of Asymmetric Bounding

Let $\mathcal{A}$ be the universe of all conceivable on-chain execution actions $(v, a, q, m)$, where:
* $v \in \mathcal{V}$: Execution venue contract address.
* $a \in \mathcal{T}$: Token asset.
* $q \in \mathbb{R}^+$: Order size in USD.
* $m \in \{\text{AUTO}, \text{PROPOSE}, \text{BREAKOUT}, \text{BLOCKED}\}$: Autonomy execution mode.

### The Econometric Admissible Space $\mathcal{B}_{\text{math}}$
The deterministic multi-layer econometric filters define the bounded feasible space:

$$\mathcal{B}_{\text{math}} = \left\{ (v, a, q, m) \in \mathcal{A} \;\middle|\; \begin{aligned}
&v \in \mathcal{V}_{\text{whitelist}}, \\
&q \le \min(Q^*_{\text{mandate}}, \; \text{TetherRadius}_{\text{remaining}}), \\
&\Delta(t) = R_{\text{cons}}(t) - \text{Baseline}^*(t) < 0, \\
&\beta_{\text{OLS}} < 1.0 \quad (\text{Stationary Reversion}), \\
&\text{EV}_{\text{adj}} \ge +15\text{ bps}
\end{aligned} \right\}$$

### The AI Candidate Space $\mathcal{B}_{\text{AI}}$
The probabilistic AI Brain proposes a decision $\mathbf{d}_{\text{AI}} = (v_{\text{AI}}, a_{\text{AI}}, q_{\text{AI}}, m_{\text{AI}})$.

### The Asymmetric Bounding Theorem
The system enforces that the final executed transaction $\mathbf{d}^*$ satisfies:

$$\mathbf{d}^* = \Pi_{\mathcal{B}_{\text{math}}}(\mathbf{d}_{\text{AI}}) \in \mathcal{B}_{\text{math}}$$

Where the projection operator $\Pi$ is defined by:
1. **Venue Filtering:** If $v_{\text{AI}} \notin \mathcal{V}_{\text{whitelist}}$, then $\mathbf{d}^* = \emptyset$ (`REJECT`).
2. **Monotonic Capital Truncation:**
   $$q^* = \min(q_{\text{AI}}, \; Q^*_{\text{math}})$$
3. **Monotonic Autonomy Demotion:**
   $$m^* = \max(m_{\text{AI}}, \; m_{\text{math}}) \quad \text{under order } \text{AUTO} < \text{PROPOSE} < \text{BREAKOUT} < \text{BLOCKED}$$

---

## 2. Corollary: Impossibility of Model Drift Exploits

**Theorem 1:** *No probabilistic hallucination, adversarial prompt injection, or parameter drift in the LLM can cause an unwhitelisted transfer, breach the daily tether limit, or execute a non-positive carry trade.*

**Proof:**  
Suppose an adversarial prompt induces the LLM to output $q_{\text{AI}} = \$1,000,000$ to an unknown recipient $v_{\text{hacker}}$ with mode $m_{\text{AI}} = \text{AUTO}$.  
1. `validate_verdict()` in `agent/tecc_brain/graph/brain.py` evaluates $v_{\text{hacker}} \in \mathcal{V}_{\text{whitelist}}$. Result: `False`.
2. $q_{\text{AI}} \le \text{baseline\_auto\_usd}$. Result: `False`.
3. The validator discards the LLM verdict and triggers `report_from_decision()`, falling back to the conservative rules baseline.
4. On-chain, `TetherGuardHook.sol` enforces `spending + amount <= tetherRadius` and `whitelistedTargets[target] == true`. Even if off-chain code were modified, the transaction reverts at the EVM state transition level. $\blacksquare$

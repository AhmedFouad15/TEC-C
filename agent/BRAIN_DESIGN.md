# Tec-C Brain — Member 2 Design Spec (Cognitive AI & Strategy Engine)

Owner: Member 2 · Deadline: Oct 20, 2026 23:59 Beijing · Lives in `/agent` (Python 3.11, FastAPI, LangGraph, Pydantic v2, web3.py)

The Brain turns a sentence ("Stake my 10 ETH") into a ranked, risk-priced plan, decides whether it may act
alone or must ask, and **learns from every user reaction** so its choices fit that user over time.
It never holds the master key: it only signs with an ephemeral session key, and the Vault (Member 1)
reverts anything outside the on-chain tether no matter what the Brain decides.

> **v2 (Oct 16) — mentor feedback applied.** The mentor's review of the PegGuard idea asked for:
> a fair-value benchmark from redemption rights and reserves (not moving averages); three regimes
> (normal / temporary liquidity distress / fundamental peg failure); recovery probability, time and loss
> instead of mean-reversion speed; costs under panic liquidity; contagion handled at portfolio level; and
> asset-specific hedging instead of one delta-neutral recipe. Sections 2.2, 2.4–2.6 implement this.
> The single change in spirit: **the sentinel no longer asks "is the news bad?" — it asks "is this a
> temporary mispricing or a permanent capital impairment?"**

---

## 1. Pipeline (LangGraph state machine)

```
parse ─▶ privacy_sieve ─▶ profile ─▶ scan_markets ─▶ regime ─▶ hard_filters ─▶ score ─▶ portfolio_check ─▶ rank
                                     (Member 4)      (§2.4)                    (§2.2)      (§2.5)          │
                                                                                                           ▼
                                     learn ◀── on-chain review events ◀── execute ◀── autonomy_gate (§2.3)
                                                                                     ├─ AUTO     → sign + submit
                                                                                     ├─ PROPOSE  → wait for user pick
                                                                                     └─ BREAKOUT → FaceID (Member 3)
```

| Node | What it does |
|---|---|
| `parse` | LLM → `Mandate` Pydantic model `{action, asset, amount, amount_usd, constraints, horizon}`. Deterministic regex fallback if the LLM is down (demo failsafe). Rejects instructions that change recipients/limits ("send all to 0x…") — prompt-injection firewall. |
| `privacy_sieve` | Replaces balances/addresses/DIDs with tokens (`<BAL_1>`, `<ADDR_1>`) before any cloud LLM call; restores locally. |
| `profile` | Loads the user's learned `UserModel` (§3) from local storage. Never sent to the cloud. |
| `scan_markets` | Calls Member 4's feeds: yields, peg prices, pool depth, redemption status, FinBERT entity sentiment. Mock JSON fallback. |
| `regime` | Classifies every pegged asset held or targeted: normal / distress / failure (§2.4). |
| `hard_filters` | Drops any candidate that breaks a rule (§2.1). |
| `score` | Risk-adjusted excess return in % per year (§2.2). |
| `portfolio_check` | Contagion-adjusted exposure per cluster (§2.5); may add "reduce exposure" cards. |
| `rank` | Good / Better / Best. |
| `autonomy_gate` | AUTO / PROPOSE / BREAKOUT and the size of the autonomous slice. |
| `execute` | ERC-7579 `execute` calldata, UserOp, EIP-712 `UserMandate` digest, session-key signature (`sessionKey ‖ sig ‖ mandateDigest`, 117 bytes). Pre-flight dry-run via Member 4. |
| `learn` | Consumes on-chain review events and user picks → updates `UserModel` (§3). |

---

## 2. How the Brain assesses an option

### 2.1 Hard filters (never learned, never overridden)

A candidate is removed if any of these hold:

1. Asset/protocol tier > user's tier (mirrors `targetRiskTiers` on-chain; tier 3 = any).
2. Target not in the account's whitelist (unless tier 3).
3. **Failure veto:** any asset the trade buys or deposits into has `P(failure) ≥ 0.30` (§2.4).
4. **Negative recovery edge:** buying a de-pegged asset whose recovery-adjusted edge `E ≤ 0` (§2.4).
5. Pre-flight slippage > 0.5% or pool depth < 5× trade size.
6. Brain's own heartbeat stale (`isAIHeartbeatAlive == false`) → re-ping before anything.

Sentiment alone never vetoes. A ≥ 60% negative FinBERT score with an entity match **removes autonomy**
(PROPOSE only) and feeds the regime model. Why: a sentiment-only veto would have dumped USDC at $0.88 in
March 2023, turning a temporary mispricing into a realised loss. That is exactly what the mentor warned about.

The veto lives in the Brain, not on-chain: Vault Sovereignty says sentiment must never freeze the vault.
Learning can only move the Brain *inside* these walls.

### 2.2 Score: risk-adjusted excess return (the "weights")

Every number is in **% per year**, so every term has an economic meaning a finance judge can check:

```
score = (APY − hurdle) − (1 + λ) · PD · LGD − c_in − c_out_stress + w_a · a
```

| Term | Meaning | Source |
|---|---|---|
| `hurdle` | 1Y **Shibor**: the onshore risk-free rate. If DeFi can't beat it after risk, don't take the risk. | Member 4 |
| `PD` | Probability of **permanent impairment** over one year: `1 − (1 − pd_base)·(1 − P_failure)` | `protocols.json` + §2.4 |
| `LGD` | Loss given impairment, from reserve quality: fiat/T-bill reserves ≈ 0.10–0.25, crypto-collateral ≈ 0.4, algorithmic ≈ 0.9 | `protocols.json` |
| `c_in` | Gas + slippage to enter, annualised over the mandate horizon | pre-flight |
| `c_out_stress` | Cost to **exit during a panic**: slippage at 30% of today's depth + hurdle × redemption delay | feeds + `protocols.json` |
| `a` | Learned like/dislike of this protocol, −1…+1; `w_a` = 0.3 %/yr | `UserModel` (§3) |
| `λ` | **Loss aversion**: how much more the user hates a loss than they like an equal gain | `UserModel` |

`(1 + λ)` makes the formula a loss-averse expected return: λ = 0 is risk-neutral, λ = 3 counts each dollar of
expected loss four times.

| Tier | λ start | λ band (learning stays inside) | approval threshold θ | max share of NAV per stablecoin cluster |
|---|---|---|---|---|
| Conservative (1) | 3.0 | 2.0 – 5.0 | 0.80 | 60% |
| Balanced (2) | 1.0 | 0.5 – 2.0 | 0.70 | 50% |
| Aggressive (3) | 0.3 | 0.0 – 0.8 | 0.60 | 40% |

(The cluster cap gets *tighter* as the tier gets more aggressive. Aggressive users hold more volatile assets,
so a stablecoin cluster failing hits them while they have the least liquid cushion. Conservative users hold
mostly stables, and their cap is spread across issuers with independent reserves.)

A negative score means "not worth the risk versus Shibor". If every option is negative, the Brain says so and
recommends the money-market rail instead of forcing a trade.

**Good / Better / Best**
- **Good**: the literal thing the user asked for (e.g. Lido stake), if it passes the filters.
- **Better**: the highest score that fits inside the autonomous limit (can run now, no FaceID).
- **Best**: the highest score overall (may need Breaking the Tether).

**Sanity check with the demo numbers** (Balanced, λ = 1, hurdle 2.15%, all values %/yr):

| Option | APY | excess | PD · LGD | (1+λ)·EL | c_out_stress | score |
|---|---|---|---|---|---|---|
| Lido stake | 3.10 | 0.95 | 0.5% · 0.30 = 0.15 | 0.30 | 0.10 | **+0.55** |
| Curve stETH/ETH LP | 6.85 | 4.70 | 1.5% · 0.40 = 0.60 | 1.20 | 0.50 | **+3.00** → Best |
| Aave USDC | 4.20 | 2.05 | 0.8% · 0.25 = 0.20 | 0.40 | 0.05 | **+1.60** → wins the USDC scene |
| PAXG carry | 1.80 | −0.35 | 0.3% · 0.10 = 0.03 | 0.06 | 0.20 | **−0.61** |

Both demo scripts fall out of the formula, and the cards can now say *"Curve: +3.0%/yr after expected
losses and panic-exit cost"* instead of an unitless score.

### 2.3 Autonomy gate (act alone vs ask)

The Brain keeps its own **soft tether** *below* the Vault's hard one:

```
soft_limit = (0.5 + 0.5·τ) × remaining_on_chain_radius        τ = Brain trust score, 0…1, starts 0.6
```

It executes **AUTO** only if all of these hold:
1. amount ≤ `soft_limit` and `score > 0`
2. `P(approve | protocol, action) ≥ θ` (posterior mean, §3.1)
3. every pegged asset touched has `P(normal) ≥ 0.80` and its cluster is not under stress (§2.5)
4. no ≥ 60% negative FinBERT hit on a matched entity
5. the intent is routine (deposit/stake/rebalance into an already-used protocol). First use of a protocol, and every de-peg opportunity → PROPOSE.

If amount > `soft_limit` the Brain **splits**: it runs the part that fits automatically and proposes the rest.
With τ = 0.6 and a $500 radius: soft limit = 0.8 × 500 = **$400**, exactly the demo's "routes $400 into Aave".
If the user picks an option above the on-chain radius → **BREAKOUT** (Member 3's FaceID modal).

### 2.4 Peg regime model: temporary mispricing vs permanent impairment

For each pegged asset (USDC, USDT, DAI, stETH, rETH, PAXG, …):

**Fair value from fundamentals, not moving averages**
```
FV = coverage × (1 − redemption_fee) / (1 + hurdle × redemption_delay_years)
```
`coverage` comes from the latest reserve attestation (cash + T-bills ÷ supply), haircut for reserves known to
be frozen (e.g. SVB deposits). For stETH, FV is the ETH redeemable through the Lido withdrawal queue, discounted
for the queue wait.

**Inputs** (normalised 0–1, from Member 4 unless noted)

| Symbol | Input |
|---|---|
| `g` | peg gap `1 − price/peg` |
| `s` | FinBERT P(negative) for the matched entity |
| `R` | redemption status: 0 open · 0.5 delayed/limited · 1 paused |
| `q` | reserve quality (static table: T-bills/cash ≈ 0.95, over-collateralised crypto ≈ 0.7, algorithmic ≈ 0.2) |
| `L` | liquidity stress: pool imbalance / drop in depth vs 7-day average |
| `k` | contagion: `max_j ρ_ij · P_failure(j)` over the asset's cluster (§2.5) |

**Regime probabilities** (softmax, normal = 0)
```
z_distress = −4 + 60·min(g, 0.08) + 2s + 3L + 2k        ← saturates: big gaps are not "temporary"
z_failure  = −7 + 30·g + 3s + 4R + 4(1 − q) + 3k
[P_normal, P_distress, P_failure] = softmax([0, z_distress, z_failure])
```
The coefficients are hand-set and checked against three real episodes. We say so openly in the pitch; fitting
them on more events is future work:

| Episode | g | s | R | q | L | P_normal / P_distress / P_failure | What happened |
|---|---|---|---|---|---|---|---|
| USDC, SVB (Mar 2023), $0.88 | 0.12 | 0.85 | 0.5 | 0.95 | 0.9 | 0.01 / **0.97** / 0.02 | recovered in ~3 days |
| stETH, Celsius (Jun 2022), 0.94 ETH | 0.06 | 0.60 | 1.0 | 0.95 | 0.8 | 0.04 / **0.88** / 0.08 | recovered |
| UST (May 2022), $0.70 | 0.30 | 0.80 | 0.5 | 0.20 | 0.9 | 0.00 / 0.01 / **0.99** | failed |
| USDC, a normal day | 0.001 | 0.10 | 0 | 0.95 | 0.05 | **0.97** / 0.03 / 0.00 | — |

This answers the mentor's challenge directly: we never extrapolate historical mean-reversion speed. Recovery is
inferred from **whether the mechanism still works**: redemptions open, reserves intact, liquidity coming back.

**Recovery-adjusted edge** for buying a de-pegged asset at price `p`:
```
P_rec = P_normal + P_distress
E = P_rec·(FV − p) − P_failure·(p − V_fail) − c_in − c_out_stress − hurdle × T_rec
```
`V_fail = q × FV` is what is left if it fails, and `T_rec` is the expected recovery time (distress median ≈ 7 days).
- USDC at $0.88 → E ≈ **+11%**: a "buy the discount" opportunity card (PROPOSE only, never AUTO).
- UST at $0.95 (early in the crash, P_failure ≈ 0.23) → E ≈ **−14%**: blocked, and the Brain proposes exiting.

### 2.5 Portfolio contagion: one de-peg raises the odds of others

Assets are grouped into clusters that share backing or redemption paths, with hand-set links `ρ_ij`
(for example DAI ← USDC = 0.8, because DAI is largely backed by USDC through its peg stability module; in March
2023 DAI fell to ~$0.90 alongside USDC):

| Cluster | Members | Example links |
|---|---|---|
| USD fiat-backed | USDC, USDT, FDUSD, DAI | DAI←USDC 0.8 · USDT↔USDC 0.3 |
| ETH-pegged | stETH, rETH, ezETH | ezETH←stETH 0.6 · rETH↔stETH 0.4 |
| Gold-backed | PAXG, XAUT | 0.2 |

`portfolio_check` does three things:
1. Adds the contagion term `k` to every member before regimes are computed (§2.4), so a USDC shock raises DAI's PD.
2. Computes the expected loss of the **whole portfolio**: `Σ w_i · PD_i · LGD_i`, using contagion-adjusted PDs.
3. If any cluster member has `P_distress + P_failure > 0.5`, it stops all AUTO trades into the whole cluster. If the cluster is over its tier cap (§2.2), it adds a **"reduce cluster exposure"** card sized to bring portfolio expected loss back under the user's limit.

### 2.6 Asset-specific responses (no generic delta-neutral hedge)

Shorting BTC/ETH against a stablecoin adds unrelated market risk, and shorting another stablecoin adds new
counterparty risk. So the Brain uses a per-asset playbook:

| Asset | Distress (temporary) | Failure (permanent) |
|---|---|---|
| Fiat-backed USD stable | Hold if redemptions reopen within T_rec; no new deposits; propose discount purchase if E > 0 | Exit to the onshore money-market rail (Shibor MMF / e-CNY) **outside** the affected cluster; this needs FaceID |
| stETH / LSTs | Hold: the discount is redeemable via the withdrawal queue; propose discount purchase if E > 0 | Unwind to native ETH (direct exposure to the underlying, not a short) |
| PAXG | Check the latest reserve attestation; hold if coverage holds | Redeem to custodian or exit to USD rail |
| Algorithmic stable | Never auto-held (q ≈ 0.2 keeps PD high) | Exit immediately |

---

## 3. Personalisation: rewards and penalties

### 3.1 What is learned (`UserModel`, stored locally per account)

| State | Type | Start |
|---|---|---|
| `λ` loss aversion | float, clamped to tier band | tier start |
| `τ` Brain trust | float 0…1 | 0.6 |
| `approval[(protocol, action)]` | Beta(α, β) | Beta(2, 2) |
| `notes` | list of structured preferences from review notes | [] |

Affinity used in the score: `a = 2·(α/(α+β)) − 1`.

### 3.2 Signals → updates

Every signal comes from an **on-chain event** (auditable) or an explicit UI choice. `v` is a value weight so
tiny trades can't farm trust: `v = clamp(1 + log10(usd / 100), 0.5, 2.0)`.

| Signal | Source | approval Beta | τ (trust) | λ (loss aversion) |
|---|---|---|---|---|
| 👍 Ratify | `TransactionRatified` | α += 1·v | +0.02·v | — |
| 👎 Flag for revert | `TransactionFlaggedForRevert` | β += 3 | −0.15 | ×1.10 |
| 📝 Note + penalty | `TransactionNoteSubmitted(penalize=true)` | β += 1.5 | −0.07 | parsed from note |
| 📝 Note, no penalty | `TransactionNoteSubmitted(penalize=false)` | ±0.5 by note sentiment | — | parsed from note |
| Accept breakout | `SignApprovalSubmitted(true)` | α += 1 | +0.01 | — |
| Reject breakout | `SignApprovalSubmitted(false)` | β += 2 | −0.05 | ×1.05 |
| Picks a **safer** card than "Best" | UI choice | chosen α += 0.5 | — | ×1.05 |
| Picks a **riskier** card than "Better" (incl. accepting a de-peg opportunity) | UI choice | chosen α += 0.5 | — | ×0.95 |
| Ignores proposal 24h | timeout | — | — | — |

Rules that keep it safe:
- **Asymmetric:** one flag (−0.15) costs as much trust as ~7 ratifies.
- **Daily cap:** τ can rise at most +0.05 per day (mirrors the Vault's 10%/day growth cap). Falls are uncapped.
- **Bands:** λ never leaves the tier band; moving tiers is the user's call only.
- **Forgetting:** α, β decay toward the prior with a 30-day half-life.
- **Notes:** an LLM turns "stop using Curve, I hate IL" into `{protocol: curve, polarity: −1, factor: c_out_stress}` → β += 1 for Curve and that cost term ×1.1 for this user. Notes are data, never instructions (a note cannot raise limits or add recipients).
- **No exploration with money:** Thompson sampling may reorder *cards shown to the user*; autonomous trades always use the posterior mean.
- **Learning never touches the regime model.** User feedback personalises *how much loss this user tolerates*, not *what the market's state is*.

### 3.3 How the Brain uses the on-chain levers

| Lever | When the Brain pulls it |
|---|---|
| `calibrateDynamicRadius` (Vault grows radius ≤10%) | Only if τ ≥ 0.70 **and** 7-day approval rate ≥ 0.80 **and** ≥ 3 ratifications. |
| `autonomousRadiusAdjustment` (decrease) | Shrinks its own radius by 10% after 2 flags in 7 days, or while a held cluster is under stress (§2.5). Never to 0 (contract reverts on 0). |
| `recordAIHeartbeat` | Every 12 h from a scheduler. |

---

## 4. API (for Member 3)

| Endpoint | Purpose |
|---|---|
| `POST /api/mandate/parse` | text → `Mandate` |
| `POST /api/mandate/propose` | `Mandate` → Good/Better/Best cards with the full score breakdown + autonomy decision |
| `POST /api/mandate/execute` | chosen card → UserOp (or breakout request) |
| `GET  /api/risk/regimes` | per-asset `P_normal/P_distress/P_failure`, FV, cluster stress: drives the Security Radar |
| `GET  /api/profile/{account}` | λ, τ, tier, soft limit, top likes/dislikes: the "Your Brain" panel |
| `POST /api/review/sync` | pull review events from chain → `learn` (also on a timer) |
| `POST /api/profile/onboard` | 5-question quiz → tier + λ prior |
| `POST /api/backtest/{episode}` | replay USDC-SVB / stETH-Celsius / UST through the regime model (demo + pitch slide) |

---

## 5. Open items with the team

1. **`shared/contracts.json` is not in the repo** and `script/export_shared_artifacts.py` hard-codes Windows paths. Ask Ahmed to commit it, or we generate it locally with `forge build`.
2. **Units:** the export says `tetherRadiusDefaultWei = 0.5 ETH`, but `TetherGuardHook` measures radius in **8-decimal USD**. The Brain uses USD×1e8. Confirm with Ahmed.
3. **Member 4's plan says "shrink Tether Radius to $0 on exploits".** This conflicts with Vault Sovereignty, and `autonomousRadiusAdjustment(0)` reverts. The veto stays in the Brain.
4. **One `mandateRoot` per session key:** each user mandate gets its own session key registration (through the account, signed by the root owner in Member 3's UI).
5. **Member 4 must now also supply:** peg prices, pool depth + 7-day average, redemption status, reserve attestation coverage. Static fallbacks ship in `/agent/data/`.
6. **Pitch/docs wording:** replace "veto if negative news ≥ 60%" with "temporary mispricing vs permanent impairment (3-regime model)". Suggested Scene 2: two headlines, one USDC/SVB-style (Brain *holds* and offers the discount), one UST-style (Brain *exits the whole cluster*). That shows the mentor's point live.

## 6. Build order

| Day | Deliverable |
|---|---|
| Oct 16 | FastAPI scaffold, `Mandate` model, `/parse` with LLM + regex fallback, privacy sieve |
| Oct 17 | Tier profiles, `protocols.json`, regime model + backtest of the 3 episodes, scoring, `/propose` with mock feeds; unit tests on all numbers in this doc |
| Oct 18 | Portfolio contagion, `UserModel` + learning + event listener; EIP-712 mandate + UserOp encoder against Anvil |
| Oct 19 | `/execute`, Member 4 feeds live, Member 3 integration, `/profile` + `/risk/regimes` |
| Oct 20 | `requirements.txt`, OpenAPI docs, freeze |

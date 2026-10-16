# Tec-C Brain (Member 2 — Cognitive AI & Strategy Engine)

## What This Is

The off-chain "Brain" of Tec-C, an AI agent wallet for the Shenzhen FinTechathon 2026 (Topic F). It turns a
user's sentence ("Stake my 10 ETH", "Optimize my $1,500 USDC") into a risk-priced Good/Better/Best plan,
decides whether it may act alone inside the on-chain Tether Radius or must ask the user, signs bounded
transactions with an ephemeral session key, and personalises itself from the user's rewards and penalties.
It sits between Member 3's frontend, Member 4's market/NLP feeds and Member 1's ERC-7579 vault.

## Core Value

**The risk engine must be right and defensible:** the 3-regime peg model (normal / temporary distress /
permanent failure), fair value from fundamentals, and loss-averse risk-adjusted scoring that reproduces the demo
numbers and the historical episodes (USDC-SVB, stETH-Celsius, UST). This is what judges and the mentor examine.

## Requirements

### Validated

<!-- Existing, built by Member 1 (Ahmed) in this repo — the Brain integrates with these, does not change them. -->

- ✓ TecAccount (ERC-7579) with `execute` / `executeFromExecutor` and pre/post hooks — existing
- ✓ TetherGuardHook: USD-normalised (8-dec, Chainlink) daily Tether Radius, asset tiers 1–3, whitelist — existing
- ✓ Morning Review: `ratifyTransaction`, `flagTransactionForRevert` (−20%), `submitTransactionNote` (optional −10%) — existing
- ✓ `calibrateDynamicRadius` (+10%/day max), `autonomousRadiusAdjustment` (decrease any time, never 0) — existing
- ✓ Breaking the Tether: 5-minute biometric window + sign approvals — existing
- ✓ AI heartbeat watchdog (`recordAIHeartbeat`, 48h) — existing
- ✓ SessionKeyValidator: session key + `mandateRoot`, signature = `sessionKey(20) ‖ sig(65) ‖ mandateDigest(32)` — existing
- ✓ 156 Foundry tests passing — existing

### Active

Risk engine (core):
- [ ] Protocol/asset static table (`protocols.json`): tier, pd_base, LGD, reserve quality q, redemption fee/delay, cluster
- [ ] Fair value from reserve coverage + redemption terms (not moving averages)
- [ ] 3-regime softmax model with documented coefficients; reproduces the 4 episode rows in BRAIN_DESIGN.md §2.4
- [ ] Recovery-adjusted edge E for de-pegged assets (+3.0% USDC-SVB after reserve haircut and 30-day recovery, −14.2% UST early)
- [ ] Score in %/yr: excess over Shibor − (1+λ)·PD·LGD − c_in − c_out_stress + w_a·a; reproduces §2.2 demo table
- [ ] Hard filters (tier, whitelist, failure veto, negative edge, slippage, heartbeat)
- [ ] Portfolio contagion (clusters, ρ links, cluster caps, "reduce exposure" cards)
- [ ] Asset-specific response playbook (no generic delta-neutral)
- [ ] Good / Better / Best ranking + autonomy gate (soft tether, split sizing, AUTO / PROPOSE / BREAKOUT)
- [ ] Backtest endpoint replaying the 3 historical episodes

Intent & privacy:
- [ ] `Mandate` Pydantic model; rule-based parser (always works offline)
- [ ] Pluggable LLM parser interface (provider undecided; offline parser is the default and fallback)
- [ ] Prompt-injection firewall (no new recipients / limit changes from text or notes)
- [ ] Privacy sieve: mask balances/addresses/DIDs before any cloud call, restore locally

Adaptive learning:
- [ ] `UserModel` (λ, τ, Beta approvals, notes) persisted locally per account
- [ ] Reward/penalty updates from on-chain events + UI picks, asymmetric, daily cap, tier bands, 30-day decay
- [ ] Note parsing into structured preferences (data, never instructions)
- [ ] On-chain levers policy: when to call calibrate / decrease radius / heartbeat

On-chain integration:
- [ ] Load ABIs/addresses (`shared/contracts.json` or local `forge build`)
- [ ] EIP-712 `UserMandate` digest + session-key signature in the 117-byte format
- [ ] Submit via direct `account.execute` / `executeFromExecutor` on local Anvil (no bundler)
- [ ] Event listener for review/approval events → learning
- [ ] Pre-flight dry-run (eth_call) before submit

Data:
- [ ] Market data adapter: Member 4 feed when available; else live public sources (DeFiLlama yields, CoinGecko peg prices, Shibor) ; else bundled snapshot. Every value tagged with its source.

API & demo:
- [ ] FastAPI: `/api/mandate/parse|propose|execute`, `/api/risk/regimes`, `/api/profile/{account}`, `/api/profile/onboard`, `/api/review/sync`, `/api/backtest/{episode}`; OpenAPI docs
- [ ] Brain demo page (single static page served by FastAPI): regimes, score breakdown, learning state, backtest — for the video, separate from Member 3's app
- [ ] `requirements.txt`, README for `/agent`, tests for every number in BRAIN_DESIGN.md

### Out of Scope

- Real ERC-4337 bundler / EntryPoint submission — user decision; direct `execute` on Anvil is enough for the demo
- Changing Member 1's Solidity contracts — not our module; raise issues with Ahmed instead
- Member 3's main Next.js app — Brain only exposes API + its own debug/demo page
- FinBERT model hosting — Member 4 owns it; Brain consumes P(negative) per entity (mock until then)
- Fitting regime coefficients on a large dataset — hand-set and validated on 3 episodes, stated openly as future work
- Real-money mainnet deployment

## Context

- Event: Shenzhen FinTechathon 2026 (Tsinghua PBCSF & WeBank), Topic F Agent Wallet. Judging: task completion 40%, security 30%, innovation/UX 30%.
- Team of 4: Member 1 Ahmed (vault, done), Member 2 Khalid (this), Member 3 frontend, Member 4 NLP + oracles + simulator.
- Full design spec: `agent/BRAIN_DESIGN.md` (v2, includes mentor feedback). Briefing PDFs in `~/Downloads/hackathon with ahmed`.
- Mentor feedback (Oct 16): sentiment+mean-reversion alone is not innovative; distinguish temporary mispricing from permanent impairment; fair value from fundamentals; 3 regimes; recovery probability/time/loss; stressed liquidity costs; contagion at portfolio level; asset-specific hedging. NLP sentinel "very promising".
- Vault Sovereignty invariant (Member 1): sentiment never freezes the vault on-chain; penalties only throttle the Brain.
- Known integration issues: `shared/contracts.json` not committed and export script hard-codes Windows paths; export says radius in wei but hook uses USD×1e8; Member 4's "$0 radius on exploit" conflicts with contract (reverts on 0); one mandateRoot per session key.
- Local env: macOS, Python 3.13 (no 3.11), no Foundry/Anvil installed yet, no LLM API key set.

## Constraints

- **Timeline**: Submission Oct 20, 2026 23:59 Beijing (= 17:59 Cairo) — team sync wants backend frozen by Oct 20 18:00 Beijing.
- **Tech stack**: Python + FastAPI + Pydantic v2 + web3.py (team spec); LangGraph named in spec — use it only if it doesn't cost reliability; plain typed pipeline acceptable.
- **Reliability**: Demo must run fully offline (no LLM key, no internet) with deterministic results — failsafe playbook in the spec.
- **Security**: Brain never holds master keys; notes and parsed text can never add recipients or raise limits.
- **Git**: local branch `member2/brain` in Ahmed's repo; never push without the user's say-so; no Co-Authored-By lines.
- **Python**: 3.13 locally; keep deps compatible with 3.11 (team spec).

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Score in %/yr with (1+λ)·PD·LGD loss term | Economically interpretable, answers mentor's "economically justified" | — Pending |
| 3-regime softmax, hand-set coefficients checked on USDC-SVB / stETH / UST | Mentor's core ask; transparent and testable in 4 days | — Pending |
| Sentiment alone never vetoes; P_failure ≥ 0.30 or E ≤ 0 does | Avoid selling temporary mispricings at a loss | — Pending |
| Veto + learning live in the Brain, not on-chain | Vault Sovereignty invariant | — Pending |
| Soft tether (0.5+0.5τ)·remaining radius, τ₀ = 0.6 | Reproduces demo's $400 autonomous slice; trust-scaled autonomy | — Pending |
| Asymmetric rewards/penalties, value-weighted, daily cap | Prevents reward hacking, mirrors vault 10%/day | — Pending |
| LLM provider undecided → offline rule parser first, LLM pluggable | Team hasn't decided; demo must work offline | — Pending |
| Direct account.execute on Anvil, no bundler | User scoped out ERC-4337 bundler | — Pending |
| Live data with source tags + bundled snapshot fallback | User wants live data; demo must not depend on internet | — Pending |
| Build own Brain demo page served by FastAPI | User wants it for the video; no dependency on Member 3 | — Pending |

---
*Last updated: 2026-10-16 after initialization*

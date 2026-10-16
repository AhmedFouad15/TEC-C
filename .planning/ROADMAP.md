# Roadmap: Tec-C Brain (Member 2)

## Overview

Build the off-chain Brain from the inside out: first the typed data and static tables, then the risk engine
that is the project's core value (fair value, 3-regime peg model, loss-averse scoring), then portfolio-level
strategy and the autonomy gate, then the user-facing pieces (intent parsing, privacy, adaptive learning, API),
then real execution against Ahmed's vault on Anvil, and finally live data, the Brain demo page and the freeze.
Every number in `agent/BRAIN_DESIGN.md` becomes a unit test, so the pitch numbers are provably what the code does.

## Domain Expertise

None

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Foundation** - `/agent` package, typed models, static protocol table, offline market snapshot
- [x] **Phase 2: Risk Engine** - Fair value, 3-regime model, recovery edge, %/yr score, hard filters (TDD on spec numbers)
- [ ] **Phase 3: Portfolio & Strategy** - Contagion, cluster caps, playbook, Good/Better/Best, autonomy gate, backtest
- [ ] **Phase 4: Intent & Privacy** - Offline mandate parser, prompt-injection firewall, privacy sieve, pluggable LLM
- [ ] **Phase 5: Adaptive Learning** - UserModel, reward/penalty updates, note parsing, onboarding, on-chain lever policy
- [ ] **Phase 6: API Layer** - FastAPI pipeline + all endpoints + OpenAPI spec for Member 3
- [ ] **Phase 7: On-Chain Integration** - Anvil deploy, EIP-712 mandate, session-key signing, execute, event → learning
- [ ] **Phase 8: Live Data, Demo Page & Freeze** - Public data adapters, Brain demo page, README, requirements freeze

## Phase Details

### Phase 1: Foundation
**Goal**: A runnable, tested `/agent` Python package with all domain models and the offline data the risk engine needs
**Depends on**: Nothing (first phase)
**Research**: Unlikely (standard Python/Pydantic/FastAPI setup)
**Plans**: 2 plans

Plans:
- [x] 01-01: Package scaffold (pyproject/requirements, venv, pytest, FastAPI `/health`) + Pydantic domain models (Mandate, Asset, PegState, MarketSnapshot, Candidate, Card, Decision)
- [x] 01-02: `protocols.json` (tier, pd_base, LGD, q, redemption fee/delay, cluster, ρ links) + bundled market snapshot + `MarketDataSource` adapter interface with snapshot implementation

### Phase 2: Risk Engine
**Goal**: The core value — economically justified, deterministic risk math that reproduces every number in BRAIN_DESIGN.md §2.2 and §2.4
**Depends on**: Phase 1
**Research**: Unlikely (formulas fully specified in BRAIN_DESIGN.md)
**Plans**: 3 plans (TDD)

Plans:
- [x] 02-01: Fair value + 3-regime softmax model — tests reproduce the 4 episode rows (USDC-SVB, stETH, UST, normal)
- [x] 02-02: Recovery-adjusted edge (+3.1% / −14%) + %/yr score with (1+λ)·PD·LGD and stressed exit cost — tests reproduce the demo table
- [x] 02-03: Hard filters (tier, whitelist, failure veto, negative edge, slippage/depth, heartbeat) with reason codes

### Phase 3: Portfolio & Strategy
**Goal**: Turn per-asset scores into portfolio-aware, explainable decisions: what to show and whether to act alone
**Depends on**: Phase 2
**Research**: Unlikely (internal logic, spec defined)
**Plans**: 3 plans

Plans:
- [ ] 03-01: Contagion propagation over clusters + portfolio expected loss + cluster caps + "reduce exposure" cards
- [ ] 03-02: Candidate generation per intent, Good/Better/Best ranking, autonomy gate (soft tether, split sizing, AUTO/PROPOSE/BREAKOUT) — reproduces the $400 Aave and Curve-Best demo scenes
- [ ] 03-03: Asset-specific response playbook + backtest runner replaying the 3 historical episodes as time series

### Phase 4: Intent & Privacy
**Goal**: Safely turn natural language into a typed Mandate, offline-first, immune to injected instructions
**Depends on**: Phase 1
**Research**: Unlikely (offline parser first; LLM is an interface only until provider is decided)
**Plans**: 2 plans

Plans:
- [ ] 04-01: Rule-based mandate parser (demo sentences + variants) + prompt-injection firewall (TDD with attack strings from the demo script)
- [ ] 04-02: Privacy sieve (mask/restore balances, addresses, DIDs) + `IntentParser` protocol with optional LLM adapter that falls back to rules

### Phase 5: Adaptive Learning
**Goal**: The Brain personalises λ, τ and per-protocol approval from rewards and penalties, safely bounded
**Depends on**: Phase 3
**Research**: Unlikely (update rules specified in BRAIN_DESIGN.md §3)
**Plans**: 3 plans

Plans:
- [ ] 05-01: `UserModel` + JSON persistence + update rules for every signal in §3.2 (asymmetry, value weight, daily cap, bands, decay) — TDD
- [ ] 05-02: Note parsing into structured preferences (rule-based, LLM-optional) treated as data + 5-question onboarding quiz → tier & λ prior
- [ ] 05-03: On-chain lever policy (when to calibrate / shrink radius / heartbeat) as pure decision functions + learning wired into scoring (affinity, θ)

### Phase 6: API Layer
**Goal**: A documented FastAPI service Member 3 can build against today, running the full pipeline end-to-end on offline data
**Depends on**: Phases 3, 4, 5
**Research**: Likely (decide LangGraph vs plain typed pipeline)
**Research topics**: Current LangGraph StateGraph API and its cost in deps/reliability vs a plain node pipeline with the same shape
**Plans**: 3 plans

Plans:
- [ ] 06-01: Pipeline orchestrator (parse → sieve → profile → scan → regime → filters → score → portfolio → rank → gate) with trace output
- [ ] 06-02: `/api/mandate/parse|propose|execute` (execute returns an unsigned execution plan until Phase 7) + `/api/risk/regimes`
- [ ] 06-03: `/api/profile/*`, `/api/review/sync` (simulated events), `/api/backtest/{episode}` + export `shared/api_spec.json`

### Phase 7: On-Chain Integration
**Goal**: The Brain's decisions become real, vault-checked transactions on a local Anvil chain, and on-chain reviews feed learning
**Depends on**: Phase 6
**Research**: Likely (external tooling and exact encodings)
**Research topics**: Foundry install on macOS; deploying Member 1's suite on Anvil (DeployTecC.s.sol); ERC-7579 execution calldata encoding used by TecAccount; web3.py + eth-account EIP-712 typed-data signing; session-key signature layout and executeFromExecutor auth
**Plans**: 3 plans

Plans:
- [ ] 07-01: Install Foundry, build + deploy contracts to Anvil, generate local `contracts.json`, contract loader in Python
- [ ] 07-02: EIP-712 `UserMandate` digest, session key registration flow, 117-byte signature, eth_call dry-run, `/execute` submits for real
- [ ] 07-03: Event listener (ratify / flag / note / sign approval / radius adjusted) → learning; heartbeat scheduler; lever calls

### Phase 8: Live Data, Demo Page & Freeze
**Goal**: Live-sourced numbers with honest source tags, a demo page for the video, and a reproducible frozen backend
**Depends on**: Phase 7
**Research**: Likely (external public APIs)
**Research topics**: DeFiLlama yields API, CoinGecko simple price for peg assets, a reachable Shibor source (shibor.org / fallback), rate limits and offline fallback behaviour
**Plans**: 3 plans

Plans:
- [ ] 08-01: Live `MarketDataSource` (DeFiLlama, CoinGecko, Shibor) with timeouts, caching, per-value source tags, snapshot fallback; Member 4 adapter stub
- [ ] 08-02: Brain demo page served by FastAPI: intent box, Good/Better/Best with score breakdown, regime radar, learning panel, backtest replay
- [ ] 08-03: `/agent/README.md`, frozen `requirements.txt`, one-command run script, demo rehearsal checklist, team handoff notes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8
(Phase 4 depends only on Phase 1 and may be pulled earlier if the API is needed sooner.)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 2/2 | Complete | 2026-10-16 |
| 2. Risk Engine | 3/3 | Complete | 2026-10-16 |
| 3. Portfolio & Strategy | 0/3 | Not started | - |
| 4. Intent & Privacy | 0/2 | Not started | - |
| 5. Adaptive Learning | 0/3 | Not started | - |
| 6. API Layer | 0/3 | Not started | - |
| 7. On-Chain Integration | 0/3 | Not started | - |
| 8. Live Data, Demo Page & Freeze | 0/3 | Not started | - |

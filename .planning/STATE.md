# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-16)

**Core value:** The risk engine must be right and defensible — 3-regime peg model, fundamental fair value, loss-averse %/yr scoring reproducing the spec numbers.
**Current focus:** Backend freeze (Oct 20, 18:00 Beijing). Phase 6.1 (Intake loop & AI Brain) is implemented in the working tree (not yet committed); remaining: Phase 7-03 and Phase 8.

## Current Position

Phase: 6.1 complete (uncommitted) · 7 of 8 in progress (07-01, 07-02 done; 07-03 not started)
Plan: Next — 07-03 (review events → learning, on-chain levers), then Phase 8
Status: In progress
Last activity: 2026-10-17 — Phase 6.1: draft/confirm intake loop, AI Brain single-pass synthesis, options list unified through the Brain (521 tests passing)

Progress: ████████▌░ 85% (23/27 plans)

## Test Status (2026-10-17, `cd agent && python -m pytest`)

- 521 passed, 15 skipped, 1 failed: `test_market_executors.py::test_crypto_execution_action_dispatch` needs
  Foundry build artifacts (`forge build` in `contracts/`); Foundry is not installed on the current machine.
- Demo fixtures: `python -m scripts.brain_demo` (from `agent/`) — 2 scenarios, 10 steps, all as expected.

## Performance Metrics

**Velocity:**
- Total plans completed: 23
- Average duration: 10 min (phases 1–4)

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation | 2/2 | 22 min | 11 min |
| 02-risk-engine | 3/3 | 19 min | 6 min |
| 03-portfolio-strategy | 4/4 | 46 min | 12 min |
| 04-intent-privacy | 2/2 | 35 min | 18 min |
| 05-adaptive-learning | 3/3 | — | — |
| 05.1-sharpe-cvar | 1/1 | — | — |
| 06-api-layer | 3/3 | — | — |
| 06.1-intake-ai-brain | 3/3 | — | — |
| 07-onchain-integration | 2/3 | — | — |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- 06.1 (2026-10-17, product decisions D1–D10):
  - D1: live AI / API keys are injected later by the team; backend reads them from env (`agent/.env.example`), offline fallback otherwise
  - D2: the AI Brain is strictly tighten-only (keep / size down / downgrade / reject; never loosen) — key security selling point
  - D3: an AI REJECT removes automatic execution but keeps every option visible for manual approval (never BLOCKED by the AI)
  - D4: `/evaluate_options` runs through the same AI Brain step as `/propose` — one decision loop, one `BrainReport`
  - D5: draft rate limits and injection strikes key on the account only (judges share Wi-Fi); `TECC_RATELIMIT_BY_CLIENT=1` re-enables per-IP
  - D6: account auth stays the shared `TECC_API_TOKEN` for the demo (SIWE later)
  - D7: the model may see order amounts and scores, never account id, raw text or portfolio
  - D8: `/propose` uses the upgraded CMC + Grok + CoinGlass sentinel (same as options and the hourly monitor)
  - D9: FISCO BCOS, Arbitrum and PegGuard executors are labelled `simulated: true` (they make no RPC call)
  - D10: `venue:X` in an order is a hard restriction; `avoid:X` / `venue:X` are now enforced by the planner
- 06.1: confirmed orders are locked as a structured Mandate with a content-hash version; /propose never re-parses
- 05: LangGraph chosen for Phase 6 (team notes); Sharpe & CVaR inserted as Phase 5.1 (display metrics)
- 06: API loopback-only unless TECC_API_TOKEN; proposals bound to account; headlines move sentiment only
- 05-03: levers need elasticity enabled; shrink once/24 h, floor 1 on-chain unit; dislike → never AUTO
- 05-02: positive notes never unlock a first use; cost factors bounded [1.0, 1.5]
- 05-01: event time drives decay and the daily τ cap; penalties never scaled by trade size
- Init: offline rule parser first, LLM pluggable (provider undecided)
- Init: no ERC-4337 bundler — direct account.execute on Anvil
- Init: local branch member2/brain, no push without approval
- 01-01: keep httpx (not httpx2) for TestClient — supply-chain caution
- 04: downstream consumes only firewall-normalized text; only known DIDs exempt
- 03: planner sizing fails closed; opportunities need edge ≥ 1%; T_rec 7/30/180d by redemption status
- 03: demo profile pre-seeded with Aave history (Beta(5,2)); new users never get AUTO
- 02: PD adds only regime failure above the quiet-state floor (no double count with pd_base)
- 01-02: c_out_stress = (exit_bps/1e4)/0.30/horizon + hurdle·delay/365

### Team work merged outside this roadmap (2026-10-17, Member 1 / Member 4)

- Multi-chain vault (Ethereum/Sepolia, Arbitrum One, FISCO BCOS) + cross-chain tether radius (`TetherGuardHook`)
- Upgraded News Risk Sentinel (CMC Fear & Greed + Grok + CoinGlass + FinBERT, GATE 0 veto)
- Multi-market executors + `MarketRouter` + `CrossChainTetherTracker`; 5-layer PegGuard engine + executor
- `/evaluate_options`, `/trigger_hourly_monitor`, APScheduler hourly monitor

### Deferred Issues

- ISS-001 (Phase 4): regex firewall cannot be complete — the AI Brain validator now catches a fooled model structurally (demo: `injection_refusal`), but an LLM classifier pass is still future work
- ISS-002 (Phase 4): sieve does not mask personal names — local NER before cloud calls
- ISS-003: multi-chain vault & upgraded sentinel review (Khaled)

### Blockers/Concerns

- Foundry not installed on the current machine (one test needs `forge build` artifacts)
- Execution is not wired end to end (scoped out for the demo): `MarketRouter` is not the graph's executor, `ExecutionIntent.market` is always "crypto", PegGuard is not a Brain agent, no relayer calls `syncCrossChainSpend`
- Rate limiter and draft store are in-memory: run the API as a single worker process
- Phase 6.1 changes are uncommitted in the working tree (owner will branch/commit/push)

## Session Continuity

Last session: 2026-10-17
Stopped at: Phase 6.1 complete (uncommitted) — next: 07-03, then Phase 8 (live data keys injected by the team)
Resume file: agent/INTAKE_AND_ORCHESTRATOR.md

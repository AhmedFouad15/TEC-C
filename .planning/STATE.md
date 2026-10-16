# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-16)

**Core value:** The risk engine must be right and defensible — 3-regime peg model, fundamental fair value, loss-averse %/yr scoring reproducing the spec numbers.
**Current focus:** Phase 5 — Adaptive Learning

## Current Position

Phase: 5 of 8 (Adaptive Learning)
Plan: 2 of 3 (+ inserted 5.1 Sharpe & CVaR)
Status: In progress
Last activity: 2026-10-16 — 05-02 notes + onboarding complete (326 tests)

Progress: █████░░░░░ 54% (13/24 plans)

## Performance Metrics

**Velocity:**
- Total plans completed: 11
- Average duration: 10 min
- Total execution time: 2.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation | 2/2 | 22 min | 11 min |
| 02-risk-engine | 3/3 | 19 min | 6 min |
| 03-portfolio-strategy | 4/4 | 46 min | 12 min |
| 04-intent-privacy | 2/2 | 35 min | 18 min |

**Recent Trend:**
- Last 5 plans: —
- Trend: Stable/improving

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- 05: LangGraph chosen for Phase 6 (team notes); Sharpe & CVaR inserted as Phase 5.1 (display metrics)
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

### Deferred Issues

- ISS-001 (Phase 4): regex firewall cannot be complete — add LLM classifier pass later
- ISS-002 (Phase 4): sieve does not mask personal names — local NER before cloud calls

### Blockers/Concerns

- Foundry/Anvil not installed (needed Phase 7)
- Waiting on team: shared/contracts.json, radius units (wei vs USD×1e8), Member 4 feed JSON shape

## Session Continuity

Last session: 2026-10-16
Stopped at: Phase 4 complete — next: /gsd:plan-phase 5
Resume file: None

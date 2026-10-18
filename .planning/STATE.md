# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-16)

**Core value:** The risk engine must be right and defensible — 3-regime peg model, fundamental fair value, loss-averse %/yr scoring reproducing the spec numbers.
**Current focus:** Backend freeze (Oct 20, 18:00 Beijing). Phases 6.1 (Intake loop & AI Brain) and 6.2 (System Flow Audit resolution, branch `fix/audit-resolution`) are done; remaining: Phase 7-03 and Phase 8.

## Current Position

Phase: 6.2 complete (branch `fix/audit-resolution`) · 7 of 8 in progress (07-01, 07-02 done; 07-03 not started)
Plan: Next — 07-03 (review events → learning, on-chain levers), then Phase 8
Status: In progress
Last activity: 2026-10-18 — Phase 6.2: every System Flow Audit finding (B1–B5, N1–N8) resolved; 660 Python tests

Progress: ████████▌░ 86% (26/30 plans)

## Test Status (2026-10-18, `cd agent && python -m pytest`)

- 660 Python tests: 659 pass; `test_audit_anchor.py::test_privacy_audit_anchor_client_submit_and_verify` needs a
  current `forge build` (the local `contracts/out` predates `PrivacyAuditAnchor.sol`). Regression tests for every
  audit finding: `agent/tests/test_audit_resolution.py`.
- Demo fixtures: `python -m scripts.brain_demo` (from `agent/`) — 2 scenarios, 10 steps, all as expected.

## Performance Metrics

**Velocity:**
- Total plans completed: 26
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
| 06.2-audit-resolution | 3/3 | — | — |
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

- 06.2 (2026-10-18, System Flow Audit resolution):
  - B1/B2: `/execute` enforces the Brain's per-card verdict — an AI-vetoed (BLOCKED) card is refused; an AI BREAKOUT
    always needs FaceID; only what did not already run automatically is executed, through the MarketRouter
  - B3: PegGuard never executes on its own — authorized trades pass the soft tether, the AI Brain and the router
  - B4: a configured model that times out or errors puts the order on HOLD (nothing automatic, options kept);
    an invalid verdict still falls back to the rules baseline; no model configured = rules (offline demo)
  - N2: venues carry a market; the Brain's cards and intents route to crypto / chinese_market / commodities / arbitrage

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

- Local `contracts/out` is stale (one test needs a fresh `forge build` for `PrivacyAuditAnchor`)
- Markets are live only where `scripts/deploy_market_chain.py` deployed a vault; every other market returns an honest
  `simulated` result (no transaction hash). Audit anchoring needs `TECC_AUDIT_ANCHOR_*` (else `not_configured`)
- Rate limiter, draft store, proposals and the cross-chain tether tracker are in-memory: run the API as one worker
- The phone gateway acts for one owner account per laptop (`TECC_VIRTUAL_SESSION_ACCOUNT`)

## Session Continuity

Last session: 2026-10-18
Stopped at: Phase 6.2 complete on `fix/audit-resolution` — next: 07-03, then Phase 8 (live data keys injected by the team)
Resume file: agent/INTAKE_AND_ORCHESTRATOR.md

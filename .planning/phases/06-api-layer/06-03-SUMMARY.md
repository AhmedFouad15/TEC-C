---
phase: 06-api-layer
plan: 03
subsystem: api
tags: [profile, learning, sentinel, backtest, openapi, security, tdd]
provides:
  - GET /api/profile/{account}, GET /api/profile/quiz, POST /api/profile/onboard, POST /api/review/sync,
    POST /api/levers/{account}, GET /api/backtest, POST /api/backtest/{episode}, POST /api/sentinel/headline
  - POST /api/mandate/propose accepts `headline` (Scene 2)
  - tecc_brain.sentinel: LexiconSentinel (offline FinBERT fallback), SentinelSource protocol, apply_signal
  - scripts/export_api_spec.py → shared/api_spec.json
  - api.deps.require_client (auth gate on every /api route)
key-decisions:
  - "Headlines move sentiment only; words alone never force the failure regime (SVB headline → distress up, failure < 30%)"
  - "Headlines carrying instructions are dropped (firewall) — a news feed is untrusted input too"
  - "Auth: loopback-only by default; TECC_API_TOKEN switches to Bearer-token auth for a networked demo"
  - "Execute requires the proposal's own account (404 otherwise, proposal not burned)"
issues-created: []
completed: 2026-10-16
---

# Phase 6 Plan 3: Profile, Learning Loop, Sentinel & Spec Summary

**Every BRAIN_DESIGN §4 endpoint now exists, plus levers and the headline sentinel; Member 3 has `shared/api_spec.json`.**

- RED `6918437`, GREEN `87dc589`, security tests `aa65532` (413 tests).

## Deviations
- Background security review flagged missing authentication / authorisation on the mandate endpoints. Fixed (rule 2):
  loopback-only default, optional Bearer token, proposals bound to their account. The fix code landed in `87dc589`,
  its tests in `aa65532`.
- `/api/review/sync` still trusts posted events (demo/simulator path). Phase 7 makes the chain the source.

## Next
- Phase 7: Foundry + Anvil, deploy Ahmed's contracts, UserOperation + session-key signature, executor, event listener.

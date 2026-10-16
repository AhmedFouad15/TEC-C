---
phase: 01-foundation
plan: 01
subsystem: foundation
tags: [python, fastapi, pydantic-v2, pytest]

requires: []
provides:
  - tecc_brain package with venv, pytest, GET /health
  - typed domain models with explicit unit convention
affects: [01-foundation, 02-risk-engine, 04-intent-privacy, 06-api-layer, 07-onchain-integration]

tech-stack:
  added: [fastapi 0.143, pydantic 2.14, uvicorn, pytest, httpx 0.28 (dev)]
  patterns:
    - "Rates are fractions/yr, money float USD, USD×1e8 only at the chain boundary"
    - "Static/market models frozen + extra=forbid; output models mutable"

key-files:
  created: [agent/pyproject.toml, agent/requirements.txt, agent/requirements-dev.txt, agent/tecc_brain/app.py, agent/tecc_brain/models.py, agent/tests/test_models.py, agent/tests/test_health.py]
  modified: [.gitignore]

key-decisions:
  - "Keep established httpx for TestClient; do not adopt httpx2 (unverified supply-chain risk)"
  - "Run commands with agent/.venv/bin/python"

patterns-established:
  - "Every model field documents its unit"
  - "Data entries carry a note field with rationale/source"

issues-created: []

duration: 12min
completed: 2026-10-16
---

# Phase 1 Plan 1: Package Scaffold & Domain Models Summary

**`tecc_brain` package (FastAPI + Pydantic v2) with a health endpoint and frozen, unit-documented domain models, including 8-decimal USD helpers matching TetherGuardHook**

## Performance

- **Duration:** ~12 min
- **Completed:** 2026-10-16
- **Tasks:** 2 (+1 fix)
- **Files modified:** 9

## Accomplishments
- Installable `agent/` package with venv; `pytest` green (9 tests)
- `GET /health` FastAPI endpoint
- Domain models: RiskTier (1/2/3 = vault constants), Asset, Venue, ContagionLink, PegState (validated redemption status), VenueQuote, NewsSignal, MarketSnapshot, Mandate, ScoreBreakdown, Candidate, Card, Decision
- `usd_to_onchain` / `onchain_to_usd` (×1e8, half-even) for the vault's USD radius

## Task Commits

1. **Task 1: Scaffold package, venv, tooling** - `ff3b5aa` (feat)
2. **Fix: replace httpx2 with httpx** - `ecf1559` (fix)
3. **Task 2: Domain models with explicit units** - `500641a` (feat)

## Files Created/Modified
- `agent/pyproject.toml` - package metadata, pytest config, warning filter
- `agent/requirements*.txt` - runtime and dev deps
- `agent/tecc_brain/app.py` - FastAPI app + /health
- `agent/tecc_brain/models.py` - all domain models + unit convention
- `agent/tests/` - health and model tests
- `.gitignore` - venv, caches, agent/var

## Decisions Made
- `note` field added to static models now (planned for 01-02) so data files can carry rationale.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Security] Removed httpx2 dependency**
- **Found during:** Task 1
- **Issue:** Starlette 1.8 warns to use `httpx2`; I installed it to silence the warning. A background security review flagged it as a possible typosquat. Starlette's own source does reference it, but it could not be fully verified.
- **Fix:** Reverted to the established `httpx` (dev-only) and filtered the deprecation warning in pytest config.
- **Verification:** 9 tests pass with no warnings; `pip list` shows only httpx/httpcore.
- **Committed in:** `ecf1559`

---

**Total deviations:** 1 auto-fixed (security)
**Impact on plan:** None on scope; safer dependency set.

## Issues Encountered
None beyond the dependency deviation.

## Next Phase Readiness
- Ready for 01-02 (reference data + market snapshot)

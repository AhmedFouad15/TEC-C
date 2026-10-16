---
phase: 02-risk-engine
plan: 02
subsystem: risk-engine
tags: [scoring, expected-loss, recovery-edge, tdd]

requires:
  - phase: 02-risk-engine
    provides: assess_peg, PegAssessment.failure_excess, fair_value
provides:
  - score_venue → ScoreBreakdown in fractions/yr
  - entry_cost, stressed_exit_cost, venue_pd, recovery_edge
affects: [02-risk-engine, 03-portfolio-strategy, 05-adaptive-learning, 06-api-layer]

tech-stack:
  added: []
  patterns:
    - "Code output is the source of truth for pitch numbers; spec tables updated to match"

key-files:
  created: [agent/tecc_brain/risk/score.py, agent/tests/test_score.py]
  modified: [agent/BRAIN_DESIGN.md]

key-decisions:
  - "STRESS_DEPTH_FACTOR 0.30, AFFINITY_WEIGHT 0.003, DEFAULT_RECOVERY_DAYS 7 as named constants"
  - "venue_pd returns pd_base exactly when no live excess (no float noise)"

patterns-established:
  - "ScoreBreakdown terms always sum to total (tested)"

issues-created: []

duration: 8min
completed: 2026-10-16
---

# Phase 2 Plan 2: Recovery Edge & %/yr Score Summary

**Loss-averse %/yr venue score and recovery-adjusted de-peg edge: Curve +2.98% > Aave +1.59% > Lido +0.54% > PAXG −0.64%; USDC at $0.88 = +3.1%, UST at $0.95 = −14%**

## TDD Cycle
- **RED** (`2145249`): 19 tests — cost formulas, PD de-duplication, demo table, ordering, breakdown sum, λ monotonicity, affinity weight, both episode edges.
- **GREEN** (`01e4031`): `tecc_brain/risk/score.py`. One float-noise failure fixed by returning pd_base exactly when no excess. 70/70 green.
- **REFACTOR:** none.

## Deviations from Plan
- Spec table §2.2 updated to code outputs (each within 0.03 pts of the old hand numbers): live calm-day peg risk adds ~0.01 to (1+λ)·EL; PAXG entry cost −0.03.
- Strengthened `test_edge_shrinks_as_failure_risk_grows` to exercise `recovery_edge` directly.

## Issues Encountered
None.

## Next Phase Readiness
- Filters (02-03) can use `recovery_edge` output for NEGATIVE_EDGE and PegAssessment for FAILURE_VETO

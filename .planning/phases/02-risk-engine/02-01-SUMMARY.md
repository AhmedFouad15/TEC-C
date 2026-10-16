---
phase: 02-risk-engine
plan: 01
subsystem: risk-engine
tags: [regime-model, fair-value, softmax, tdd]

requires:
  - phase: 01-foundation
    provides: PegState/Asset models, episodes.json, SnapshotSource
provides:
  - fair_value, regime_probabilities, quiet_failure_floor, assess_peg
  - RegimeProbs (dominant, p_recover), PegAssessment (failure_excess)
affects: [02-risk-engine, 03-portfolio-strategy, 06-api-layer]

tech-stack:
  added: []
  patterns:
    - "Model coefficients are named module constants (exposable via API for transparency)"
    - "Pure functions, no I/O, in tecc_brain/risk/"

key-files:
  created: [agent/tecc_brain/risk/regime.py, agent/tests/test_regime.py]
  modified: []

key-decisions:
  - "Price above peg counts as gap 0 (premium is not distress)"
  - "failure_excess = p_failure − quiet floor(q) so annual pd_base is not double counted"

patterns-established:
  - "Reference episodes are the regression suite for the model"

issues-created: []

duration: 6min
completed: 2026-10-16
---

# Phase 2 Plan 1: Fair Value & 3-Regime Peg Model Summary

**Fundamental fair value plus a normal/distress/failure softmax that reproduces USDC-SVB, stETH-Celsius, UST and a normal day to ±0.005**

## TDD Cycle
- **RED** (`8cc5383`): 20 tests — 5 episodes × 3 probabilities, dominant regime per episode, FV cases, sum-to-one, contagion monotonicity, distress saturation, premium handling, quiet floor, snapshot assessments. Failed at import (module absent).
- **GREEN** (`161afb6`): `tecc_brain/risk/regime.py` — numerically stable softmax, named coefficients, `assess_peg` over `PegState` + `Asset`. 51/51 suite green.
- **REFACTOR:** none needed.

## Deviations from Plan
None — plan executed as written.

## Issues Encountered
None.

## Next Phase Readiness
- `PegAssessment.failure_excess` and `fair_value` ready for 02-02 (venue PD, recovery edge)

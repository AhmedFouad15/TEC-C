---
phase: 02-risk-engine
plan: 03
subsystem: risk-engine
tags: [filters, guardrails, tdd]

requires:
  - phase: 02-risk-engine
    provides: PegAssessment, recovery_edge
provides:
  - hard_filter_reasons / passes with RejectReason codes and REASON_TEXT for UI
affects: [03-portfolio-strategy, 06-api-layer, 08-live-data-demo-freeze]

tech-stack:
  added: []
  patterns:
    - "Rejections are machine-readable codes + user-facing sentences"

key-files:
  created: [agent/tecc_brain/risk/filters.py, agent/tests/test_filters.py]
  modified: []

key-decisions:
  - "Tier 3 accounts bypass the whitelist, mirroring TetherGuardHook"
  - "Sentiment alone never vetoes (explicit test); failure veto at p_failure ≥ 0.30"
  - "Slippage estimate = entry bps + amount/depth; depth must be ≥ 5× trade"

patterns-established:
  - "Reason order = enum declaration order (stable for UI and tests)"

issues-created: []

duration: 5min
completed: 2026-10-16
---

# Phase 2 Plan 3: Hard Filters Summary

**Seven reason-coded hard filters (heartbeat, tier, whitelist, failure veto, negative edge, depth, slippage) — bad news alone provably never vetoes**

## TDD Cycle
- **RED** (`be582d1`): 21 tests incl. "sentiment alone never vetoes", SVB-level distress not vetoed, forced failure vetoed, stable multi-reason order, text for every reason.
- **GREEN** (`a5851a0`): `tecc_brain/risk/filters.py`; 91/91 suite green.
- **REFACTOR:** none.

## Deviations from Plan
None.

## Issues Encountered
None.

## Next Phase Readiness
- Phase 2 complete. Phase 3 composes regime + score + filters into candidates, portfolio contagion, Good/Better/Best and the autonomy gate.

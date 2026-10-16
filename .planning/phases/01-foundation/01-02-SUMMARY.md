---
phase: 01-foundation
plan: 02
subsystem: data
tags: [reference-data, market-snapshot, importlib-resources]

requires:
  - phase: 01-foundation
    provides: domain models (Asset, Venue, ContagionLink, MarketSnapshot)
provides:
  - reference data (12 assets, 8 venues, 9 contagion links, 5 episodes) with rationale notes
  - MarketDataSource protocol + SnapshotSource (demo, usdc_distress)
affects: [02-risk-engine, 03-portfolio-strategy, 08-live-data-demo-freeze]

tech-stack:
  added: []
  patterns:
    - "Bundled JSON read via importlib.resources (CWD-independent)"
    - "Every data entry has a note explaining its value"

key-files:
  created: [agent/tecc_brain/reference.py, agent/tecc_brain/data/assets.json, agent/tecc_brain/data/venues.json, agent/tecc_brain/data/contagion.json, agent/tecc_brain/data/episodes.json, agent/tecc_brain/data/snapshot_demo.json, agent/tecc_brain/data/snapshot_usdc_distress.json, agent/tecc_brain/market/base.py, agent/tecc_brain/market/snapshot.py]
  modified: []

key-decisions:
  - "Stressed exit cost formula c_out = (exit_bps/1e4)/0.30/horizon + hurdle·delay/365; venue params tuned so it reproduces BRAIN_DESIGN §2.2"
  - "UST coverage 1.0 (mint/burn claim) with q 0.20; weakness lives in q, not FV"
  - "Contagion links only within a cluster (enforced by test)"

patterns-established:
  - "Scenario snapshots (e.g. usdc_distress) drive demo scenes deterministically"

issues-created: []

duration: 10min
completed: 2026-10-16
---

# Phase 1 Plan 2: Reference Data & Market Snapshot Summary

**Rationale-annotated asset/venue/contagion/episode tables plus offline demo and SVB-distress snapshots behind a MarketDataSource interface — 31 tests green**

## Performance

- **Duration:** ~10 min
- **Completed:** 2026-10-16
- **Tasks:** 2
- **Files modified:** 13

## Accomplishments
- 12 assets (USDC, USDT, DAI, FDUSD, UST, stETH, rETH, ezETH, PAXG, XAUT, ETH, WBTC) with q, LGD, PD, redemption terms
- 8 venues; exit parameters reproduce the spec's stressed exit costs (0.10 / 0.50 / 0.05 / 0.20 %/yr) — verified numerically
- 9 contagion links (USDC→DAI 0.8 etc.), 5 episodes with expected regime probabilities for Phase 2 tests
- `SnapshotSource("demo")` with exact pitch APYs; `SnapshotSource("usdc_distress")` replays SVB for demo Scene 2

## Task Commits

1. **Task 1: Reference data + loader** - `599181f` (feat)
2. **Task 2: MarketDataSource + snapshots + integrity tests** - `19b6eef` (feat)

## Files Created/Modified
- `agent/tecc_brain/data/*.json` - static tables and two snapshots
- `agent/tecc_brain/reference.py` - cached loader via importlib.resources
- `agent/tecc_brain/market/` - protocol + snapshot source
- `agent/tests/test_reference.py`, `test_snapshot.py` - integrity tests

## Decisions Made
See frontmatter key-decisions.

## Deviations from Plan
- Asset count is 12 (plan's example said 13); all planned assets present.
- Added `agent/tecc_brain/data/__init__.py` so importlib.resources can address the data package.

**Total deviations:** 2 trivial. **Impact:** none.

## Issues Encountered
None.

## Next Phase Readiness
- Phase 2 (risk engine) can be pure functions over `load_reference()` + `MarketSnapshot`
- Episode `expected` values are the TDD targets for 02-01 and 02-02

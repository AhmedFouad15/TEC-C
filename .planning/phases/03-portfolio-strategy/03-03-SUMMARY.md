---
phase: 03-portfolio-strategy
plan: 03
subsystem: strategy
tags: [planner, autonomy-gate, ranking, tdd]
requires:
  - phase: 03-portfolio-strategy
    provides: assess_market, portfolio_risk, playbook cards
  - phase: 02-risk-engine
    provides: score_venue, hard_filter_reasons
provides:
  - plan(mandate, snapshot, portfolio, profile, vault, ref) → Decision
  - BrainProfile (approval Beta, affinity), VaultState, APPROVAL_THRESHOLDS, demo profile
affects: [04-intent-privacy, 05-adaptive-learning, 06-api-layer, 08-live-data-demo-freeze]
tech-stack:
  added: []
  patterns:
    - "Every card explains itself line by line with the numbers"
    - "Only one option (BETTER) may ever run autonomously"
key-files:
  created: [agent/tecc_brain/strategy/planner.py, agent/tecc_brain/data/profile_demo.json, agent/tests/test_planner.py]
  modified: [agent/tecc_brain/models.py, agent/tecc_brain/strategy/playbook.py]
key-decisions:
  - "New users never get AUTO; demo profile carries 3 prior Aave ratifications (Beta(5,2))"
  - "GOOD for optimize = lowest expected loss with score ≥ −0.1%/yr (the Shibor rail)"
  - "Bad news (≥60%) on a venue's protocol removes autonomy, never vetoes"
issues-created: []
duration: 12min
completed: 2026-10-16
---

# Phase 3 Plan 3: Planner & Autonomy Gate Summary

**One call turns a mandate into an explainable Decision: Scene 1 auto-routes $400 into Aave (+1.72% for this user, +0.13% from their history), Scene 3 recommends Curve (+2.98%) over Lido (+0.54%) behind FaceID**

## TDD Cycle
- **RED** (`becc36b`): 12 tests (profile model, radius math, both scenes, rejections, breakdown sums, cold start, stressed cluster, conservative tier, heartbeat, spent radius).
- **GREEN** (`dd35715`): 131/131 green after two additions below.

## Deviations from Plan
- [Rule 1 - Bug] Two auto-eligible cards could both have run alone and overwritten the auto amount; now only BETTER can be AUTO.
- [Rule 2 - Explainability] Cards state the personal-preference term; opportunities sorted by edge (2 tests added).
- Added `Decision.rejected` so the UI can list filtered options with reasons.

## Next Phase Readiness
- Phase 4 (intent) produces the Mandate this consumes; Phase 5 updates BrainProfile; Phase 6 exposes plan() over HTTP.

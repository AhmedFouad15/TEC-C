---
phase: 05-adaptive-learning
plan: 03
subsystem: learning
tags: [levers, tether-radius, heartbeat, personalisation, tdd]
requires:
  - phase: 05-adaptive-learning
    provides: profile history, preferences, cost_factors
provides:
  - learning.levers.lever_actions(profile, LeverState, now) → heartbeat / shrink / calibrate actions
  - learning.levers.approval_rate (7-day)
  - score_venue(cost_factors=...) ; planner.protocol_stance ; disliked protocols never AUTO
affects: [06-api-layer, 07-onchain-integration]
tech-stack:
  added: []
  patterns: ["Lever decisions are pure; Phase 7 sends them"]
key-files:
  created: [agent/tecc_brain/learning/levers.py]
  modified: [agent/tecc_brain/risk/score.py, agent/tecc_brain/strategy/planner.py]
key-decisions:
  - "Shrink and calibrate both require elasticity enabled (contract reverts otherwise); LeverState defaults to disabled"
  - "Shrink: at most once per 24 h, floor = 1 on-chain unit; shrink reason blocks calibrate in the same round"
  - "Calibrate sends no radius: the vault computes its own +10% (calibrateDynamicRadius)"
  - "Latest note about a protocol wins; a dislike removes autonomy but the option is still shown"
issues-created: []
duration: 12min
completed: 2026-10-16
---

# Phase 5 Plan 3: Lever Policy & Personalised Scoring Summary

**Heartbeat every 12 h; self-shrink −10% after 2 flags in 7 days or a stressed held cluster (never to 0, once a day); calibrate only at τ ≥ 0.70, ≥80% approval, ≥3 ratifies, after the 24 h cooldown. Learned cost weights and protocol likes/dislikes now change the scores and card text; demo numbers unchanged.**

## TDD Cycle
- **RED** (`d18868e`): 22 tests (levers, score cost factors, planner preferences).
- **GREEN** (`9a5d440`): 348/348 green.

## Note for the team
- The vault already cuts the radius 20% on every flag and 10% on a penalised note. The Brain's own −10% after
  2 flags stacks on top: on-chain penalty for the event, Brain self-limit for the pattern.

## Deviations from Plan
- `last_shrink_at` lives in LeverState (read from AutonomousRadiusAdjusted on-chain) instead of the profile.

## Next Phase Readiness
- Phase 5 complete. Next: Phase 5.1 (Sharpe & CVaR), then Phase 6 API (LangGraph pipeline).

---
phase: 05-adaptive-learning
plan: 01
subsystem: learning
tags: [personalisation, rewards, penalties, persistence, tdd]
requires:
  - phase: 01-foundation
    provides: BrainProfile, APPROVAL_PRIOR
provides:
  - models.Signal, FeedbackEvent, LAMBDA_START, LAMBDA_BANDS; BrainProfile learning fields
  - learning.update.learn / decay / new_profile / value_weight → LearningResult(profile, changes, applied)
  - learning.store.ProfileStore (JSON per account, atomic, traversal-safe)
affects: [05-adaptive-learning, 06-api-layer, 07-onchain-integration]
tech-stack:
  added: []
  patterns: ["Learning is pure: new profile copy + human-readable change lines", "event_id idempotency so chain re-sync is safe"]
key-files:
  created: [agent/tecc_brain/learning/update.py, agent/tecc_brain/learning/store.py]
  modified: [agent/tecc_brain/models.py, .gitignore]
key-decisions:
  - "Event time (not wall clock) drives decay and the daily τ cap, so late-synced chain events land on the right day"
  - "Penalties are never scaled by trade size; only rewards use the value weight"
  - "Approval Betas stay keyed by venue_id (venue = protocol + action)"
  - "Anything starting 0x must be a full address; all account keys lowercased"
issues-created: []
duration: 15min
completed: 2026-10-16
---

# Phase 5 Plan 1: Learning Update Rules & Profile Store Summary

**Every §3.2 signal moves α/β, τ and λ with the specified asymmetry; dust can't farm trust, τ gains cap at +0.05/day, λ stays in its tier band, old feedback halves every 30 days, and replays are no-ops**

## TDD Cycle
- **RED** (`65f4349`): 45 tests (update rules + store).
- **GREEN** (`cf9df3e`): 290/290 green.

## Deviations from Plan
- `tau_day/tau_gained_today` became `tau_gains: {date: gain}` (last 7 days) so out-of-order events use their own day's cap.
- Store: "0xZZ"-style names rejected (must be a full address); all keys lowercased (macOS case-insensitive FS).

## Next Phase Readiness
- 05-02 fills the NOTE signal (note sentiment ±0.5, protocol preferences, cost factors) and adds onboarding.

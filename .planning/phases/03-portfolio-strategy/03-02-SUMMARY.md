---
phase: 03-portfolio-strategy
plan: 02
subsystem: strategy
tags: [playbook, hedging, opportunity, tdd]
requires:
  - phase: 03-portfolio-strategy
    provides: MarketView, PortfolioRisk
provides:
  - respond → PlaybookEntry (HOLD / HOLD_NO_NEW_DEPOSITS / EXIT + destination)
  - reduce_exposure_cards, opportunity_cards
affects: [03-portfolio-strategy, 06-api-layer]
tech-stack:
  added: []
  patterns: ["Recovery-adjusted edge carried in Candidate.apy for OPPORTUNITY cards"]
key-files:
  created: [agent/tecc_brain/strategy/playbook.py]
  modified: [agent/tecc_brain/models.py, agent/tecc_brain/data/snapshot_usdc_distress.json]
key-decisions:
  - "Algorithmic stables exit unless clearly normal (p_failure < 5%)"
  - "Cap-breach trims come from the highest-loss-rate position in the cluster"
  - "DAI coverage 0.96 in SVB snapshot: ~half its collateral was impaired USDC"
issues-created: []
duration: 8min
completed: 2026-10-16
---

# Phase 3 Plan 2: Asset-Specific Playbook Summary

**Per-asset responses (stables → onshore rail, LSTs → native ETH, never shorts), exit/trim cards for failure and cap breaches, and proposal-only "buy the discount" cards when the recovery edge is positive**

## TDD Cycle
- **RED** (`884a8b6`): 13 tests incl. "temporary distress alone never triggers selling" and "no shorts or delta-neutral hedges anywhere".
- **GREEN** (`95f8e7b`): 117/117 green.

## Deviations from Plan
- [Rule 1 - Data bug] DAI coverage in the SVB snapshot was 1.0 although its collateral was largely impaired USDC; set to 0.96 so the DAI discount isn't overstated.
- Added `Candidate.from_venue_id` so exit cards name the position they leave.

## Next Phase Readiness
- Planner (03-03) appends these cards to Decisions.

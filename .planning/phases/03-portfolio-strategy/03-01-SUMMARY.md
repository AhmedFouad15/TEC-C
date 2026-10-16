---
phase: 03-portfolio-strategy
plan: 01
subsystem: strategy
tags: [contagion, portfolio-risk, tdd]
requires:
  - phase: 02-risk-engine
    provides: assess_peg, venue_pd, FAILURE_VETO_THRESHOLD
provides:
  - assess_market → MarketView (contagion-adjusted assessments, ClusterStatus)
  - portfolio_risk → PortfolioRisk (cluster exposure/share, expected loss, cap breaches)
  - Position/Portfolio models, data/portfolio_demo.json
affects: [03-portfolio-strategy, 06-api-layer]
tech-stack:
  added: []
  patterns: ["Contagion is single-step from standalone odds"]
key-files:
  created: [agent/tecc_brain/strategy/market_view.py, agent/tecc_brain/strategy/portfolio.py]
  modified: [agent/tecc_brain/models.py]
key-decisions:
  - "Caps apply to stablecoin clusters only (usd_fiat, usd_algo), per spec"
  - "A position counts once per cluster even with several exposures in it"
issues-created: []
duration: 6min
completed: 2026-10-16
---

# Phase 3 Plan 1: Contagion Market View & Portfolio Risk Summary

**Single-step contagion (DAI ← 0.8·USDC failure odds), stressed-vs-failing cluster status, and per-tier stablecoin cluster caps with contagion-adjusted portfolio expected loss**

## TDD Cycle
- **RED** (`c17fc90`): 13 tests (calm market, SVB stress without failure, DAI contagion exact, failing USDC raises DAI, no feedback, unknown pegs, caps, EL hand calc, venue positions, empty portfolio).
- **GREEN** (`49ccdea`): 104/104 green.
- **REFACTOR:** none.

## Deviations from Plan
None.

## Next Phase Readiness
- MarketView + PortfolioRisk feed the playbook (03-02) and planner (03-03).

---
phase: 04-intent-privacy
plan: 01
subsystem: intent
tags: [prompt-injection, firewall, parser, tdd]
requires:
  - phase: 01-foundation
    provides: Mandate, Reference
provides:
  - firewall.scan → FirewallVerdict (threats, recipients, normalized) + THREAT_TEXT
  - rules.parse → ParseOutcome (offline mandate parser)
affects: [04-intent-privacy, 05-adaptive-learning, 06-api-layer]
tech-stack:
  added: []
  patterns: ["Firewall runs on every text input (requests, LLM output, notes)"]
key-files:
  created: [agent/tecc_brain/intent/firewall.py, agent/tecc_brain/intent/rules.py]
  modified: []
key-decisions:
  - "Pseudo-addresses like 0xHacker count as recipients"
  - "Relative amounts ('half my USDC') come from raw vault positions; non-USD assets carry amount_usd"
  - "Transfers are out of scope for the Brain"
issues-created: []
duration: 10min
completed: 2026-10-16
---

# Phase 4 Plan 1: Injection Firewall & Rule Parser Summary

**Every demo attack (override/drain to 0xHacker, radius change, unlimited approval, ENS recipient, zero-width and full-width tricks) is refused; all demo sentences parse offline**

## TDD Cycle
- **RED** (`f160798`): 33 tests.
- **GREEN** (`1a4e15d`): 178/178 green.

## Deviations from Plan
None.

## Next Phase Readiness
- 04-02 wraps `rules.parse` behind IntentParser with an LLM adapter and privacy sieve.

---
phase: 04-intent-privacy
plan: 02
subsystem: intent
tags: [privacy, llm, fallback, prompt-injection, tdd]
requires:
  - phase: 04-intent-privacy
    provides: firewall.scan, rules.parse
provides:
  - sieve.mask / mask_payload / restore
  - IntentParser protocol, RulesParser, LLMParser(complete) with fallback, default_parser()
affects: [05-adaptive-learning, 06-api-layer]
tech-stack:
  added: []
  patterns:
    - "Downstream code consumes only verdict.normalized (no filter/model differential)"
    - "LLM provider is a plain callable; no SDK dependency"
key-files:
  created: [agent/tecc_brain/intent/sieve.py, agent/tecc_brain/intent/parser.py]
  modified: [agent/tecc_brain/intent/firewall.py, agent/tecc_brain/intent/rules.py]
key-decisions:
  - "Only the user's own known DIDs are exempt from recipient detection"
  - "Firewall adds a squashed/leetspeak pass and an OBFUSCATION threat"
issues-created: [ISS-001, ISS-002]
duration: 25min
completed: 2026-10-16
---

# Phase 4 Plan 2: Privacy Sieve & LLM Parser Summary

**The model only ever sees firewall-approved, masked text; every failure (timeout, bad JSON, unknown asset, attack in its output) falls back to the offline parser — and attacks never reach the model at all**

## TDD Cycle
- **RED** (`70ccb06`): 22 tests (sieve masking/round-trip/payload; LLM masked prompt, fallbacks, smuggled recipients, attacks never reach model).
- **GREEN** (`156e0fb`): 221/221 green after the firewall fixes below.

## Deviations from Plan

### Auto-fixed Issues
**1. [Rule 1 - Bug] DID false positive** — a request naming the user's own WeIdentity DID was refused (embedded address). Fixed via known-identities allowlist.

**2. [Rule 2 - Security] Firewall bypass classes** (three background security reviews) — `c2aae7b`
- Cyrillic/Greek/small-caps look-alikes, mixed scripts, split/punctuated/leetspeak keywords, spaced addresses, base64 blobs, DID payee smuggling, and filter-vs-model differential (model now receives `verdict.normalized`). 20+ new tests, normal requests (incl. Chinese) still pass.

**3. [Rule 2 - Privacy] Sieve leaks** (background security review)
- Numbers glued to words ("10ETH"), payload numbers under non-"balance" keys or address keys, uppercase/64-hex/spaced/base58/bech32 addresses leaked. Now every number is masked except structural payload keys (tier, horizon_days…), and address detection is widened. 9 tests.

### Deferred Enhancements
- ISS-001: regex firewall cannot be complete; add classifier pass once an LLM provider is chosen.
- ISS-002: sieve does not mask personal names / number words; add local NER before any cloud call.

## Next Phase Readiness
- Phase 5 runs the firewall on Morning Review notes; Phase 6 exposes parse via API.

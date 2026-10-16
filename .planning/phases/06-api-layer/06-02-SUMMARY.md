---
phase: 06-api-layer
plan: 02
subsystem: api
tags: [fastapi, endpoints, cors, tdd]
provides:
  - POST /api/mandate/parse | /propose (→ proposal_id) | /execute ; GET /api/risk/regimes
  - api.deps: ProposalCache (TTL 1 h, max 500, atomic claim), get_store/get_proposals/get_ref overrides, Scenario, VaultIn
key-decisions:
  - "Execute checks the card amount against the proposal's remaining radius: above → breakout_required (FaceID)"
  - "Picking GOOD over BEST → PICK_SAFER; BEST over BETTER or an OPPORTUNITY → PICK_RISKIER (learned + persisted)"
  - "A proposal executes once (atomic claim); a bad card label doesn't burn it"
  - "Refused text returns 200 with status 'refused' and threats so the UI can show why"
completed: 2026-10-16
---

# Phase 6 Plan 2: Mandate & Risk Endpoints Summary

**Member 3 can now call parse → propose → execute and the Security Radar endpoint; Scene 1 end-to-end over HTTP.**

- RED `b70db95`, GREEN `8167e84` (388 tests).

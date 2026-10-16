---
phase: 06-api-layer
plan: 01
subsystem: graph
tags: [langgraph, agents, pipeline, tdd]
provides:
  - graph.build_graph / run_pipeline → PipelineResult (status, parse, decision, intent, regimes, clusters, profile, agents)
  - planner.assess_options / decide (plan() unchanged)
  - models.ExecutionIntent (amount_onchain = USD×1e8)
key-decisions:
  - "langgraph==1.2.12 installed with --uploaded-prior-to 2026-10-02; httpx2 arrives via langsmith (pydantic org) — accepted"
  - "Refused/unparsed text ends at intake; BLOCKED decisions skip the executor; executor is a pluggable Protocol for Phase 7"
completed: 2026-10-16
---

# Phase 6 Plan 1: LangGraph Agent Pipeline Summary

**The six agents from the team notes run as a LangGraph graph; Scene 1 → AUTO $400 Aave intent (40000000000 on-chain units, pending signature); attacks stop at the gatekeeper.**

- RED `76298d3`, refactor `be72d5d`, GREEN `5253565`.

## Next
- 06-02 API endpoints, 06-03 profile/review/backtest/sentinel/spec; Phase 7 on-chain (Foundry not installed yet).

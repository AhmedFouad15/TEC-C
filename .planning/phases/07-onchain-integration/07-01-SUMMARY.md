---
phase: 07-onchain-integration
plan: 01
subsystem: onchain
tags: [anvil, foundry, deploy, eth-abi]
provides:
  - onchain.rpc.Rpc / RpcError (stdlib urllib; local or https URLs only)
  - onchain.artifacts.Contract (load from out/, encode/call/transact/deploy, decode_error, decode_logs)
  - onchain.deploy.deploy_local → LocalDeployment (saved to agent/.state/contracts.local.json)
key-decisions:
  - "Foundry 1.8.5 installed with Homebrew (bottled, homebrew-core)"
  - "eth-account 0.14.0 + eth-abi 5.2.0 pinned (installed with --uploaded-prior-to 2026-10-02); no web3.py"
  - "Deploy from Python, not a new Solidity script: Member 1's tree stays untouched (foundry.lock restored after forge build)"
  - "Radius 500 / ceiling 2000 in USD×1e8 with ETH/USD + USDC/USD mock feeds, so the hook meters USD (resolves the wei-vs-USD open item locally)"
completed: 2026-10-16
---

# Phase 7 Plan 1: Local Chain & Deployment Summary

**Ahmed's hook, validator and account deploy to Anvil from Python with USD feeds, a USDC mock and a whitelisted mock protocol per venue.**

- RED `a6c83b4`, GREEN `32dd39f`.

## Team notes (for Ahmed)
- `forge build` rewrites `foundry.lock` on macOS/Linux because it holds a Windows path key (`lib\\forge-std`).
- ERC-20 moves are metered and whitelisted by **token** address: `USDC.transfer(anyone, x)` passes the whitelist
  once USDC is whitelisted, because the hook doesn't check the transfer recipient. The Brain's firewall blocks unknown
  recipients off-chain, but an on-chain recipient check would close it for good.

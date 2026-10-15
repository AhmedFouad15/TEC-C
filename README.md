# Tec-C Smart Contracts Layer (The Vault Architect)
**Event:** Shenzhen International FinTech Competition (FinTechathon 2026) — International Track  
**Topic:** Topic F — Agent Wallet (Autonomous On-Chain Wallet)  
**Co-Hosts:** Tsinghua University PBCSF & WeBank  
**Lead Engineer:** Member 1 (Smart Contracts & Security Lead)

---

## 1. Architectural Overview

Tec-C (**Tethered Expense Corporate Card**) decouples autonomous AI cognitive planning from deterministic on-chain execution using **ERC-7579 modular account abstraction** and immutable execution hooks.

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Tec-C On-Chain Vault Model                            │
│                                                                                 │
│   ┌───────────────────────────┐           ┌─────────────────────────────────┐   │
│   │   Passkey Root Owner      │           │     AI Agent (Session Key)      │   │
│   │ (Biometric FaceID/TouchID)│           │  (LangGraph / FinBERT Mandate)  │   │
│   └─────────────┬─────────────┘           └────────────────┬────────────────┘   │
│                 │                                          │                    │
│        Direct / Breakout                           Bounded UserOps              │
│      "Breaking the Tether"                   (Within The Tether Radius)         │
│                 │                                          │                    │
│                 ▼                                          ▼                    │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                      TecAccount.sol (ERC-7579)                          │   │
│   │                                                                         │   │
│   │   [Pre-Check Hook] ──▶  TetherGuardHook.sol                             │   │
│   │                         ├── The Tether Radius ($500/day limit)          │   │
│   │                         ├── Target Protocol Whitelist                   │   │
│   │                         ├── Dual-Axis Risk Tier Enforcement             │   │
│   │                         └── PegGuard NLP Sentinel Circuit Breaker       │   │
│   │                                                                         │   │
│   │   [Execution]      ──▶  Lido Staking / Curve LP / Institutional Gateway │   │
│   │                                                                         │   │
│   │   [Post-Check Hook]──▶  WeIdentity W3C Audit Log Telemetry              │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Smart Contracts

| Contract | Standard | Description |
| :--- | :--- | :--- |
| **[`TecAccount.sol`](src/TecAccount.sol)** | ERC-7579 & ERC-4337 | Minimal modular smart account executing single & batch operations with pre/post hooks. |
| **[`TetherGuardHook.sol`](src/hooks/TetherGuardHook.sol)** | ERC-7579 Hook | **IMMUTABLE** security hook enforcing **The Tether Radius** (velocity limit), asset whitelisting, risk tiers, and FaceID breakouts. |
| **[`SessionKeyValidator.sol`](src/validators/SessionKeyValidator.sol)** | ERC-7579 Validator | Validates ephemeral AI agent ECDSA signatures bound to EIP-712 mandate digests and time bounds. |
| **[`TecPaymaster.sol`](src/paymaster/TecPaymaster.sol)** | ERC-4337 Paymaster | Anti-griefing paymaster capping session gas to `MAX_SESSION_GAS_BUDGET = 0.005 ETH`. |

---

## 3. Test Coverage & Verification

All 24 invariant and unit tests pass with 100% green status:

```bash
forge test
```

### Test Suite Results:
- `test/TetherGuardHook.t.sol`: 9/9 PASS
  - `test_ExecutionWithinTetherRadius_Succeeds`
  - `test_ExecutionExceedingTetherRadius_Reverts`
  - `test_CumulativeSpending_ExceedingRadius_Reverts`
  - `test_EpochReset_ReplenishesTetherRadius`
  - `test_UnauthorizedTarget_Reverts`
  - `test_AssetTierNotPermitted_Reverts`
  - `test_BreakingTheTether_BiometricFaceID_BypassesLimit`
  - `test_PegGuardCircuitBreaker_EmergencyVeto`
  - `test_Initialization`
- `test/SessionKeyValidator.t.sol`: 6/6 PASS
  - `test_SessionKeyRegistration`
  - `test_ValidateUserOp_Success`
  - `test_ValidateUserOp_WrongSigner_Fails`
  - `test_ValidateUserOp_RevokedSessionKey_Fails`
  - `test_ERC1271_SignatureValidation`
  - `test_ERC1271_ExpiredSignature_Fails`
- `test/TecPaymaster.t.sol`: 4/4 PASS
  - `test_DepositAccounting`
  - `test_LegitimateSponsorship_Succeeds`
  - `test_GasGriefingLoop_HaltsAtMaxQuota`
  - `test_InsufficientDeposit_RejectsSponsorship`
- `test/TecAccount.t.sol`: 5/5 PASS
  - `test_Initialization`
  - `test_Execute_WithinTetherRadius_Success`
  - `test_Execute_ExceedingTetherRadius_Reverts`
  - `test_Execute_MaliciousTargetDrain_Reverts`
  - `test_BreakingTheTether_BiometricFaceID_Success`

---

## 4. Gas Profiling Report

| Function | Avg Gas Cost | Max Gas Cost | Notes |
| :--- | :--- | :--- | :--- |
| `TecPaymaster.validatePaymasterUserOp` | **5,920** | 6,385 | Lightweight griefing check |
| `SessionKeyValidator.validateUserOp` | **7,330** | 10,126 | ECDSA + time range unpack |
| `SessionKeyValidator.isValidSignature` | **7,753** | 9,662 | EIP-1271 magic check |
| `TetherGuardHook.getRemainingRadius` | **6,751** | 7,235 | View helper for frontend gauge |
| `TetherGuardHook.preCheck` | **44,956** | 63,157 | Complete tether + whitelist check |

---

## 5. Deployment & Shared Handoff

Deploy locally with Foundry:
```bash
# Launch Anvil testnet
anvil

# In a separate terminal, deploy Tec-C suite
forge script script/DeployTecC.s.sol --broadcast --rpc-url http://127.0.0.1:8545
```

Export compiled ABIs to `/shared/contracts.json`:
```bash
python script/export_shared_artifacts.py
```

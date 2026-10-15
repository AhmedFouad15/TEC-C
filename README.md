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
│   │   Passkey Root Owner      │           │     AI Brain (Session Key)      │   │
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
│   │                         ├── Axis 1: Asset Universe (Tiers 1, 2, 3)      │   │
│   │                         ├── Axis 2: Dynamic Tether Radius Elasticity    │   │
│   │                         ├── On-Chain 10% Daily Increase Cap             │   │
│   │                         ├── Asynchronous Morning Review (Like/Rev/Note) │   │
│   │                         ├── Brain Discretionary Quota Throttling        │   │
│   │                         └── PegGuard NLP Sentinel Circuit Breaker       │   │
│   │                                                                         │   │
│   │   [Execution]      ──▶  Lido / Aave / Curve / Shibor MMF / Institutional│   │
│   │                                                                         │   │
│   │   [Post-Check Hook]──▶  Execution Logging & Invariant Telemetry         │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Security Invariants

### 🏛️ Invariant 1: Vault Sovereignty (Never Penalize the Vault)
> **The Vault is sovereign and its capacity is NEVER limited.**
> Penalties apply strictly and exclusively to the **AI Brain's autonomous discretionary session quota** (`penalizeBrain`). When a user objects or penalizes a transaction during review, the AI Brain's autonomous Tether Radius is throttled (`tetherRadius - 10%`), but the Vault treasury, user balance, and FaceID root owner capabilities remain 100% unconstrained.

### 🛡️ Invariant 2: Independent Vault Calibration (Max 10% Daily Growth Cap)
> Dynamic limit adjustments are computed **autonomously on-chain by the Vault** via `calibrateDynamicRadius(address account)`. The on-chain Vault independently checks consecutive ratified reviews, enforcing:
> $$\text{New Radius} = \min\left(\text{Current Radius} \times 1.10,\, \text{Max Elastic Ceiling}\right)$$
> The autonomous AI Brain cannot propose its own budget increases, guaranteeing mathematically bounded growth of at most **10% per 24 hours**.

### 🌐 Invariant 3: Dual-Axis Risk Engine
- **Axis 1 (Asset Universe):**
  - **Tier 1 (Core Capital Preservation):** Mega-cap assets (BTC, ETH, SOL), fiat-backed stablecoins (USDC, USDT, e-CNY), tokenized commodities (PAXG Gold, Silver), and money-market instruments (Shibor MMF).
  - **Tier 2 (Dynamic Growth & Active DeFi):** Liquid staking (stETH, rETH), AMM liquidity pools (Uniswap, Curve), and yield vaults (Aave, Compound).
  - **Tier 3 (Omni-Universe / Unrestricted):** Allows holding **ANY** token/protocol without asset-tier restrictions, strictly safeguarded by Axis 2 velocity constraints and Layer 4 circuit breakers.
- **Axis 2 (The Tether Radius & Dynamic Elasticity):**
  - Onboarding initial tolerance: 10%, 25%, 50%, 100%, or Custom %.
  - Static Mode vs. Adaptive Learning Mode.

### ☀️ Invariant 4: Asynchronous Morning Review System
Overnight autonomous trades are recorded as `PENDING_REVIEW`. The user wakes up and can:
1. **👍 Like / Ratify (`ratifyTransaction`):** Replenishes the Tether Radius by the transaction's value and increments on-chain `consecutiveRatifications`.
2. **👎 Revert / Object (`flagTransactionForRevert`):** Flags transaction for cognitive unwind and applies a 20% trust penalty to the AI Brain's radius.
3. **📝 Note / Educate (`submitTransactionNote`):** Logs semantic educational notes to the AI Brain, with an optional penalty applied to the Brain (`penalizeBrain = true`).

---

## 3. Core Smart Contracts

| Contract | Standard | Description |
| :--- | :--- | :--- |
| **[`TecAccount.sol`](src/TecAccount.sol)** | ERC-7579 & ERC-4337 | Modular smart account executing single & batch operations with pre/post execution hooks. |
| **[`TetherGuardHook.sol`](src/hooks/TetherGuardHook.sol)** | ERC-7579 Hook | Immutable policy hook enforcing Axis 1, Axis 2, 10% daily limit growth cap, Morning Review, and PegGuard circuit breakers. |
| **[`SessionKeyValidator.sol`](src/validators/SessionKeyValidator.sol)** | ERC-7579 Validator | Validates ephemeral AI Brain ECDSA signatures bound to EIP-712 mandate digests and time bounds. |
| **[`TecPaymaster.sol`](src/paymaster/TecPaymaster.sol)** | ERC-4337 Paymaster | Anti-griefing paymaster capping cumulative gas sponsorship to `MAX_SESSION_GAS_BUDGET = 0.005 ETH`. |

---

## 4. Test Coverage & Verification

**41/41 invariant and unit tests passing with 100% green status across 4 test suites:**

```bash
forge test
```

### Complete Test Matrix:
- **`test/TetherGuardHook.t.sol` (26/26 PASS)**
  - `test_Initialization`
  - `test_ExecutionWithinTetherRadius_Succeeds`
  - `test_ExecutionExceedingTetherRadius_Reverts`
  - `test_CumulativeSpending_ExceedingRadius_Reverts`
  - `test_EpochReset_ReplenishesTetherRadius`
  - `test_UnauthorizedTarget_Reverts`
  - `test_AssetTierNotPermitted_Reverts`
  - `test_Tier1_CorePreservation_RevertsOnTier2Growth`
  - `test_Tier3_Unrestricted_AllowsAnyAssetAndProtocol`
  - `test_Tier3_Unrestricted_StillEnforcesTetherRadius`
  - `test_Tier3_Unrestricted_StillEnforcesPegGuardCircuitBreaker`
  - `test_DynamicElasticity_OptIn_StepUp_Succeeds`
  - `test_DynamicElasticity_StaticMode_Reverts`
  - `test_DynamicElasticity_ExcessiveStepUp_Reverts`
  - `test_DynamicElasticity_ExceedsCeiling_Reverts`
  - `test_DynamicElasticity_CooldownActive_Reverts`
  - `test_DynamicElasticity_DecreasingRadius_PermittedImmediately`
  - `test_VaultNative_CalibrateDynamicRadius_Succeeds`
  - `test_VaultNative_CalibrateDynamicRadius_ZeroRatifications_Reverts`
  - `test_MorningReview_LikeAndRatify_ReplenishesLimit`
  - `test_MorningReview_FlagForRevert_AppliesTrustPenalty`
  - `test_MorningReview_NoteWithoutPenalty`
  - `test_MorningReview_NoteWithPenalty`
  - `test_MorningReview_AlreadyReviewed_Reverts`
  - `test_BreakingTheTether_BiometricFaceID_BypassesLimit`
  - `test_PegGuardCircuitBreaker_EmergencyVeto`
- **`test/SessionKeyValidator.t.sol` (6/6 PASS)**
  - `test_SessionKeyRegistration`
  - `test_ValidateUserOp_Success`
  - `test_ValidateUserOp_WrongSigner_Fails`
  - `test_ValidateUserOp_RevokedSessionKey_Fails`
  - `test_ERC1271_SignatureValidation`
  - `test_ERC1271_ExpiredSignature_Fails`
- **`test/TecPaymaster.t.sol` (4/4 PASS)**
  - `test_DepositAccounting`
  - `test_LegitimateSponsorship_Succeeds`
  - `test_GasGriefingLoop_HaltsAtMaxQuota`
  - `test_InsufficientDeposit_RejectsSponsorship`
- **`test/TecAccount.t.sol` (5/5 PASS)**
  - `test_Initialization`
  - `test_Execute_WithinTetherRadius_Success`
  - `test_Execute_ExceedingTetherRadius_Reverts`
  - `test_Execute_MaliciousTargetDrain_Reverts`
  - `test_BreakingTheTether_BiometricFaceID_Success`

---

## 5. Deployment & Shared Handoff

```bash
# Launch Anvil local node
anvil

# Deploy Tec-C contracts suite
forge script script/DeployTecC.s.sol --broadcast --rpc-url http://127.0.0.1:8545

# Export ABIs and contract specifications for AI Agent and UI layers
python script/export_shared_artifacts.py
```
Outputs are automatically mirrored to:
- `shared/contracts.json` (Used by LangGraph AI Agent & Next.js UI)
- `Desktop/contracts.json`

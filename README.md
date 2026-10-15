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
│   │ (Biometric FaceID/TouchID)│           │  (LangGraph Cognitive Planner)  │   │
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
│   │                         ├── Inactive AI Heartbeat Watchdog (48h)        │   │
│   │                         ├── Corporate Dead-Man's Switch (90d)           │   │
│   │                         ├── Asynchronous Morning Review (Like/Rev/Note) │   │
│   │                         ├── Brain Discretionary Quota Throttling        │   │
│   │                         ├── Breaking the Tether: 5m Biometric Window    │   │
│   │                         └── Normal Sign Approval (Accept / Reject)      │   │
│   │                                                                         │   │
│   │   [Validation]     ──▶  WebAuthnP256Validator (RIP-7212 @ 0x100)        │   │
│   │                         └── SessionKeyValidator (EIP-712 Mandates)      │   │
│   │                                                                         │   │
│   │   [Execution]      ──▶  Lido / Aave / Curve / Shibor MMF / Institutional│   │
│   │                                                                         │   │
│   │   [Post-Check Hook]──▶  Execution Logging & Invariant Telemetry         │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Security Invariants

### 🏛️ Invariant 1: Vault Sovereignty (Never Penalize or Freeze the Vault)
> **The Vault is sovereign, and its capacity is NEVER limited or frozen.**
> 1. **No On-Chain Halts from News Sentiment:** Halting or freezing an on-chain Vault based on off-chain news sentiment causes catastrophic liquidation cascades and capital lockup. Therefore, all NLP news sentiment, depegging models, and financial sentinel intelligence belong **exclusively in the off-chain AI Cognitive Brain**, guiding internal strategy rather than freezing the on-chain vault.
> 2. **Never Penalize the Vault:** Penalties apply strictly and exclusively to the **AI Brain's autonomous discretionary session quota** (`penalizeBrain`). When a user objects or penalizes a transaction during review, the AI Brain's autonomous Tether Radius is throttled (`tetherRadius - 10%`), but the Vault treasury, user balance, and FaceID root owner capabilities remain 100% unconstrained.

### 🛡️ Invariant 2: Independent Vault Calibration (Max 10% Daily Growth Cap)
> Dynamic limit adjustments are computed **autonomously on-chain by the Vault** via `calibrateDynamicRadius(address account)`. The on-chain Vault independently checks consecutive ratified reviews, enforcing:
> $$\text{New Radius} = \min\left(\text{Current Radius} \times 1.10,\, \text{Max Elastic Ceiling}\right)$$
> The autonomous AI Brain cannot propose its own budget increases, guaranteeing mathematically bounded growth of at most **10% per 24 hours**.

### 🔐 Invariant 3: Breaking the Tether Protocol (5-Minute Biometric Window & Sign Approval)
> **"Not if they are logged in 5alas!"**
> Simply having an active session or calling as the root owner does NOT grant an automatic, indefinite bypass.
> 1. **Biometric Verification Window**: When a breakout is required (exceeding Tether Radius or accessing higher-tier assets), the AI Brain confirms user activity and triggers a biometric challenge (FaceID / TouchID / Passkey).
> 2. **5-Minute Grace Period**: Successful verification opens an on-chain 5-minute active window (`BIOMETRIC_VERIFICATION_WINDOW = 5 minutes`).
> 3. **Subsequent Brain Transactions**: If the Brain proposes any follow-up transactions during these 5 minutes, the user is **NOT** prompted for biometrics again. Instead, the user provides a simple **Sign Approval** (**Accept** or **Reject**).
> 4. **Normal Accept or Reject**: If the user accepts, the transaction executes under the active biometric window; if rejected, the transaction is immediately vetoed. Gasless signature approvals (`submitSignApprovalWithSignature`) are fully supported.
> 5. **Expiry**: Once 5 minutes elapse, the window closes and any further breakout requires fresh biometric re-verification.

### 💓 Invariant 4: Inactive AI Heartbeat & Dead-Man's Switch
> 1. **Inactive AI Heartbeat Watchdog (48h Timeout):** The AI session key must regularly broadcast an on-chain heartbeat via `recordAIHeartbeat(account)`. If $>48\text{ hours}$ elapse without an AI heartbeat, autonomous execution is automatically blocked (`AIHeartbeatStale`) until the agent is re-synced, preventing zombie key exploits.
> 2. **Corporate Dead-Man's Switch (90d Timeout):** If the primary FaceID user is inactive for $>90\text{ days}$ without interacting with the vault, a designated corporate guardian can trigger recovery via `triggerDeadmanRecovery(account, newOwner)`, transferring custody to a corporate successor. Any user activity (biometric verification, sign approval, or ping) resets the timer.

### 🌐 Invariant 5: Dual-Axis Risk Engine
- **Axis 1 (Asset Universe):**
  - **Tier 1 (Core Capital Preservation):** Mega-cap assets (BTC, ETH, SOL), fiat-backed stablecoins (USDC, USDT, e-CNY), tokenized commodities (PAXG Gold, Silver), and money-market instruments (Shibor MMF).
  - **Tier 2 (Dynamic Growth & Active DeFi):** Liquid staking (stETH, rETH), AMM liquidity pools (Uniswap, Curve), and yield vaults (Aave, Compound).
  - **Tier 3 (Omni-Universe / Unrestricted):** Allows holding **ANY** token/protocol without asset-tier restrictions, strictly safeguarded by Axis 2 velocity constraints and Biometric Breakout requirements.
- **Axis 2 (The Tether Radius & Dynamic Elasticity):**
  - Onboarding initial tolerance: 10%, 25%, 50%, 100%, or Custom %.
  - Static Mode vs. Adaptive Learning Mode.

### ☀️ Invariant 6: Asynchronous Morning Review System
Overnight autonomous trades are recorded as `PENDING_REVIEW`. The user wakes up and can:
1. **👍 Like / Ratify (`ratifyTransaction`):** Replenishes the Tether Radius by the transaction's value and increments on-chain `consecutiveRatifications`.
2. **👎 Revert / Object (`flagTransactionForRevert`):** Flags transaction for cognitive unwind and applies a 20% trust penalty to the AI Brain's radius.
3. **📝 Note / Educate (`submitTransactionNote`):** Logs semantic educational notes to the AI Brain, with an optional penalty applied to the Brain (`penalizeBrain = true`).

### 🪙 Invariant 7: Multi-Token & ERC-20 Tether Radius Inspection (Chainlink USD Normalized)
> **Values are NEVER hardcoded in ETH.**
> 1. **ERC-20 Calldata Inspection:** `TetherGuardHook` dynamically unpacks inner calldata to inspect ERC-20 method calls (`transfer`, `approve`, `transferFrom`), extracting token amounts from the parameters.
> 2. **Chainlink USD Normalization:** Converts both native ETH and arbitrary ERC-20 tokens (e.g. USDC with 6 decimals, WBTC with 8 decimals, DAI with 18 decimals) into standard 8-decimal USD via Chainlink Price Feeds (`latestRoundData`).
> 3. **Oracle Staleness & Zero-Price Guards:** Enforces strict oracle freshness ($< 24\text{ hours}$) and rejects non-positive oracle answers (`InvalidOraclePrice`, `StaleOraclePrice`).
> 4. **Unified Velocity Tracking:** Multiple token transfers accumulate against the same daily USD spending radius (`TETHER_RADIUS_USD`).
> 5. **Institutional Portfolio Valuation:** Exposes `getTotalPortfolioValueUSD(account, tokens)` returning live total portfolio value in USD (8 decimals) and detailed breakdowns (`TokenBalanceDetail[]`) showing token address, symbol, decimals, balance, USD price, and USD value.

---

## 3. Core Smart Contracts

| Contract | Standard | Description |
| :--- | :--- | :--- |
| **[`TecAccount.sol`](src/TecAccount.sol)** | ERC-7579 & ERC-4337 | Modular smart account executing single & batch operations with pre/post execution hooks. |
| **[`TetherGuardHook.sol`](src/hooks/TetherGuardHook.sol)** | ERC-7579 Hook | Immutable policy hook enforcing Axis 1, Axis 2, Multi-Token Chainlink USD normalization, 10% daily limit growth cap, 5m Biometric Window, Sign Approval (Accept/Reject), AI Heartbeat Watchdog, Dead-Man's Switch, and Morning Review. |
| **[`WebAuthnP256Validator.sol`](src/validators/WebAuthnP256Validator.sol)** | ERC-7579 & RIP-7212 | Native secp256r1 NIST P-256 validator querying precompile at `0x0100` (~3,450 gas hardware FaceID). |
| **[`SessionKeyValidator.sol`](src/validators/SessionKeyValidator.sol)** | ERC-7579 Validator | Validates ephemeral AI Brain ECDSA signatures bound to EIP-712 mandate digests and time bounds. |
| **[`TecPaymaster.sol`](src/paymaster/TecPaymaster.sol)** | ERC-4337 Paymaster | Anti-griefing paymaster capping cumulative gas sponsorship to `MAX_SESSION_GAS_BUDGET = 0.005 ETH`. |
| **[`AggregatorV3Interface.sol`](src/interfaces/AggregatorV3Interface.sol)** | Chainlink Oracle | Standard Chainlink Price Feed aggregator interface (`decimals`, `latestRoundData`). |
| **[`IERC20.sol`](src/interfaces/IERC20.sol)** | ERC-20 & Metadata | Standard ERC-20 and ERC-20 metadata interfaces (`balanceOf`, `transfer`, `approve`, `decimals`, `symbol`). |

---

## 4. Test Coverage & Verification

**81/81 invariant and security unit tests passing with 100% green status across 7 test suites:**

```bash
forge test
```

### Complete Test Matrix:
- **`test/TetherGuardHook.t.sol` (33/33 PASS)**
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
  - `test_DynamicElasticity_OptIn_StepUp_Succeeds`
  - `test_DynamicElasticity_StaticMode_Reverts`
  - `test_DynamicElasticity_ExcessiveStepUp_Reverts`
  - `test_DynamicElasticity_ExceedsCeiling_Reverts`
  - `test_DynamicElasticity_CooldownActive_Reverts`
  - `test_DynamicElasticity_DecreasingRadius_PermittedImmediately`
  - `test_VaultNative_CalibrateDynamicRadius_Succeeds`
  - `test_VaultNative_CalibrateDynamicRadius_ZeroRatifications_Reverts`
  - `test_MorningReview_LikeAndRatify_ReplenishesLimit` (With cross-epoch rollover protection)
  - `test_MorningReview_FlagForRevert_AppliesTrustPenalty`
  - `test_MorningReview_NoteWithoutPenalty`
  - `test_MorningReview_NoteWithPenalty`
  - `test_MorningReview_AlreadyReviewed_Reverts`
  - `test_BreakingTheTether_WithoutBiometric_Reverts`
  - `test_BreakingTheTether_BiometricFaceID_BypassesLimit`
  - `test_BreakingTheTether_BiometricWindowExpires_Reverts`
  - `test_BreakingTheTether_BrainInitiated_SignApproval_Accept`
  - `test_BreakingTheTether_BrainInitiated_SignApproval_Reject`
  - `test_BreakingTheTether_BrainInitiated_GaslessSignatureApproval`
  - `test_submitSignApprovalWithSignature_ExpiredDeadline_Reverts` (Signature deadline expiration)
  - `test_submitSignApprovalWithSignature_ReplayAttack_Reverts` (Anti-replay nonce protection)
  - `test_initializeAccountPolicy_FrontRunning_Reverts` (Front-running hijack protection)
  - `test_setGlobalPriceFeed_Unauthorized_Reverts` (Oracle configuration access control)
- **`test/MultiTokenTether.t.sol` (12/12 PASS)**
  - `test_ERC20Transfer_WithinTetherRadius_Success` (USDC 6 decimals normalized to USD)
  - `test_ERC20Transfer_ExceedingTetherRadius_Reverts` (USDC spending cap enforcement)
  - `test_CumulativeMultiTokenSpending_EnforcesUSDLimit` (USDC + WBTC + DAI cumulative USD tracking)
  - `test_NativeETH_NormalizedToUSD` (0.1 ETH @ $3,000/ETH = $300 USD)
  - `test_ERC20Approve_EnforcesTetherRadius` (DEX allowance velocity limit guard)
  - `test_ERC20IncreaseAllowance_EnforcesTetherRadius` (increaseAllowance inspection guard)
  - `test_StaleOraclePrice_Reverts` (Oracle older than 24 hours reverts)
  - `test_InvalidOraclePrice_Reverts` (Price $\le 0$ reverts)
  - `test_MissingOraclePriceFeed_Reverts` (Unpriced token in USD mode reverts)
  - `test_AccountSpecificPriceFeedOverride` (Per-account Chainlink oracle override)
  - `test_GetTotalPortfolioValueUSD_ReturnsAccurateValuation` (Accurate 4-asset portfolio valuation)
  - `test_BreakingTheTether_ERC20_WithBiometricAndSignApproval` (5m Biometric Grace + Sign Approval breakout)
- **`test/WebAuthnP256Validator.t.sol` (9/9 PASS)**
  - `test_PasskeyRegistration`
  - `test_VerifyP256Signature_NativePrecompile_Success`
  - `test_VerifyP256Signature_InvalidSignature_Fails`
  - `test_ValidateUserOp_Success`
  - `test_ValidateUserOp_UnregisteredPasskey_Fails`
  - `test_EIP1271_PasskeySignatureValidation`
  - `test_CompleteBiometricVerificationWithP256_OpensWindow`
  - `test_CompleteBiometricVerificationWithP256_InvalidSignature_Reverts`
  - `test_CompleteBiometricVerificationWithP256_UnregisteredPasskey_Reverts` (Spoofed coordinates rejection)
- **`test/TecPaymaster.t.sol` (6/6 PASS)**
  - `test_DepositAccounting`
  - `test_LegitimateSponsorship_Succeeds`
  - `test_GasGriefingLoop_HaltsAtMaxQuota`
  - `test_InsufficientDeposit_RejectsSponsorship`
  - `test_WithdrawForAccount_Success` (User self-withdrawal)
  - `test_WithdrawForAccount_InsufficientBalance_Reverts`
- **`test/DeadmanAndHeartbeat.t.sol` (10/10 PASS)**
  - `test_AIHeartbeat_InitialStatus_Alive`
  - `test_AIHeartbeat_Record_Success`
  - `test_AIHeartbeat_StaleTimeout_RevertsAutonomousExecution`
  - `test_AIHeartbeat_SuccessfulExecution_RefreshesHeartbeat`
  - `test_AIHeartbeat_CustomTimeout_Enforced`
  - `test_DeadmanSwitch_Configure_Success`
  - `test_DeadmanSwitch_PrematureTrigger_Reverts`
  - `test_DeadmanSwitch_ElapsedTimeout_Success`
  - `test_DeadmanSwitch_UserActivityPings_ResetsTimer`
  - `test_DeadmanSwitch_UnauthorizedCaller_Reverts`
- **`test/SessionKeyValidator.t.sol` (6/6 PASS)**
  - `test_SessionKeyRegistration`
  - `test_ValidateUserOp_Success`
  - `test_ValidateUserOp_WrongSigner_Fails`
  - `test_ValidateUserOp_RevokedSessionKey_Fails`
  - `test_ERC1271_SignatureValidation`
  - `test_ERC1271_ExpiredSignature_Fails`
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

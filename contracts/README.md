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
│   │   (Biometric Face ID)     │           │  (LangGraph Cognitive Planner)  │   │
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
> **Active Biometric Invariant (No Indefinite Session Bypass)**
> Simply having an active session or calling as the root owner does NOT grant an automatic, indefinite bypass.
> 1. **Biometric Verification Window**: When a breakout is required (exceeding Tether Radius or accessing higher-tier assets), the AI Brain confirms user activity and triggers a biometric challenge (Face ID / Passkey).
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

**156/156 invariant, scenario, fuzz, security hardening, and empirical gas benchmark tests passing with 100% green status across 12 test suites:**

```bash
forge test
```

### Complete Test Matrix (156 / 156 PASS - 100% Green across 12 Suites):
- **`test/VaultSecurityHardening.t.sol` (18/18 PASS - Core Security & Invariant Hardening)**
  - `test_LegitimateSwap_UnderLimit_Success`: (1) Legitimate swap executes under limit on DEX Router within Tether Radius.
  - `testFuzz_LegitimateSwap_UnderLimit`: Fuzzes swap amounts up to Tether Radius proving deterministic velocity deduction.
  - `test_BreachingTetherRadius_Reverts`: (2) Breaching Tether Radius strictly reverts with `TetherRadiusExceeded()`.
  - `testFuzz_BreachingTetherRadius_Reverts`: Fuzzes amounts exceeding Tether Radius proving unauthorized breakouts revert.
  - `test_UnauthorizedTarget_Reverts`: (3) Unwhitelisted target address strictly reverts with `UnauthorizedTarget()`.
  - `testFuzz_UnauthorizedTarget_Reverts`: Fuzzes arbitrary targets proving whitelist enforcement across address space.
  - `test_GasGriefing_HaltsAtMaxQuota`: (4) Algorithmic prompt-injection gas griefing halts strictly at 0.005 ETH per session.
  - `testFuzz_GasGriefing_Cap`: Fuzzes multi-step userOps proving session sponsorship never exceeds 0.005 ETH.
  - `test_SEC01_BiometricChallenge_Replay_Reverts`: Replaying a P-256 biometric challenge reverts with `ChallengeAlreadyUsed`.
  - `test_SEC01_BiometricChallenge_ExpiredDeadline_Reverts`: Expired biometric challenges revert with `ExpiredSignature`.
  - `test_SEC02_Paymaster_OwnerCannotWithdrawUserDeposits`: Owner cannot withdraw user deposits, strictly bounded by surplus.
  - `test_SEC02_Paymaster_OwnerCanWithdrawSurplus`: Owner safely withdraws surplus funds while user deposits remain fully protected.
  - `test_SEC03_Paymaster_EntryPointDepositAndWithdrawal`: Safe forwarding of deposits and withdrawals through EntryPoint.
  - `test_SEC04_Paymaster_RootOwnerECDSA_ExemptFromSessionCap`: 65-byte direct root owner ECDSA signatures exempt from session cap.
  - `test_SEC05_SessionKeyValidator_MandateBinding`: 117-byte userOps strictly verify WeIdentity mandate root commitment binding.
  - `test_SEC06_TecAccount_UninitializedRootOwner_RejectsUserOp`: Uninitialized TecAccount (`rootOwner == address(0)`) rejects validation.
  - `test_SEC07_CrossHook_SignatureReplay_Reverts`: Cross-contract signature replays rejected via `address(this)` domain separation.
  - `test_SEC08_ChainlinkOracle_IncompleteRound_Reverts`: Incomplete oracle rounds (`answeredInRound < roundId` or `updatedAt == 0`) revert.
- **`test/VaultLifecycleScenarios.t.sol` (4/4 PASS - Complex E2E Scenarios)**
  - `test_Scenario_EnterpriseMultiDayLifecycle`: 3-day corporate operational simulation (Day 1 bounded spending, overnight pending reviews, Day 2 user ratification & dynamic 10% elasticity step-up, Day 3 breakout with biometric & sign approval).
  - `test_Scenario_AttackSandbox_DefensesHold`: Comprehensive adversarial sandbox test (unauthorized initialization front-run rejection, self-targeting hook hijack rejection, unwhitelisted target denial, budget exhaustion denial, stale biometric window denial, spoofed guardian denial).
  - `test_Scenario_AIHeartbeatWatchdog_And_DeadmanRecovery`: Complete operational lifecycle of AI heartbeat expiration preventing zombie execution, user activity watchdog reset, and corporate guardian dead-man recovery after 90 days.
  - `test_Scenario_ComprehensivePortfolioBreakdown`: Institutional multi-asset portfolio breakdown querying ETH, USDC, WBTC, DAI with live Chainlink price feeds, decimals normalization, and accurate aggregate USD valuation.
- **`test/VaultComprehensiveFuzz.t.sol` (5/5 PASS - Property-Based Invariant Fuzzing - 1,280 Runs)**
  - `testFuzz_TetherRadius_VelocityEnforcement`: Invariant: Any spend $\le$ available radius succeeds; any spend $>$ available radius strictly reverts.
  - `testFuzz_DynamicElasticity_10PercentGrowthCap`: Invariant: Daily step-up is strictly bounded by $\le 10\%$ and cannot exceed the configured ceiling.
  - `testFuzz_TrustPenalty_MathematicallyStrictlyDecreases`: Invariant: Trust penalties strictly decrease the AI Brain's radius without arithmetic underflow or inversion.
  - `testFuzz_EpochRollover_ReplenishesQuota`: Invariant: Rolling over the 24-hour epoch always resets daily spending and replenishes available radius.
  - `testFuzz_Paymaster_GasSponsorshipCap`: Invariant: TecPaymaster sponsorship strictly respects gas caps and prevents account draining.
- **`test/VaultEdgeCases.t.sol` (19/19 PASS - Boundary & Edge Case Hardening)**
  - `test_EdgeCase_ModuleInstallation_OnlyRootOwner_Reverts`: Non-root callers cannot install modules.
  - `test_EdgeCase_ModuleInstallation_InvalidModuleType_Reverts`: Module type verification rejection.
  - `test_EdgeCase_ModuleUninstallation_Mismatch_Reverts`: Mismatched module uninstallation rejection.
  - `test_EdgeCase_ModuleUninstallation_InvalidType_Reverts`: Invalid module type uninstallation rejection.
  - `test_EdgeCase_ModuleUninstallation_And_Reinstallation_Success`: Seamless uninstallation and reinstallation lifecycle.
  - `test_EdgeCase_ZeroValue_EmptyCalldata_Succeeds`: Safe zero-value no-op calls.
  - `test_EdgeCase_NativeETH_ZeroDataTransfer_Success`: Direct native ETH transfers within radius.
  - `test_EdgeCase_DirectETHReceive_AcceptsDeposit`: Direct ETH receive hook accepts deposits.
  - `test_EdgeCase_Review_NonExistentRecord_Reverts`: Reviewing non-existent transaction records reverts.
  - `test_EdgeCase_Review_UnauthorizedUser_Reverts`: Unauthorized users cannot review transactions.
  - `test_EdgeCase_BiometricGrace_Revocation_ImmediatelyHaltsBreakout`: Revoking biometric grace window immediately blocks breakout.
  - `test_EdgeCase_SignApproval_ExplicitReject_PreventsExecution`: Explicit rejection halts execution with `ExecutionRejectedByUser`.
  - `test_EdgeCase_DeadmanSwitch_ZeroGuardian_Reverts`: Rejects zero-address dead-man guardian.
  - `test_EdgeCase_DeadmanSwitch_ExactBoundaryTrigger`: Strict 1-second boundary verification for dead-man switch trigger.
  - `test_EdgeCase_CustomHeartbeatTimeout_Below1Hour_Reverts`: Heartbeat timeout cannot be configured below 1 hour.
  - `test_EdgeCase_SessionKey_ZeroAddress_Reverts`: Rejects zero-address session key registration.
  - `test_EdgeCase_SessionKey_InvalidTimeRange_Reverts`: Rejects invalid session key time ranges (`validAfter > validUntil`).
  - `test_EdgeCase_Paymaster_WithdrawZeroBalance_Reverts`: Rejects zero-balance withdrawals from paymaster.
  - `test_EdgeCase_Paymaster_OwnerWithdrawal_Unauthorized_Reverts`: Non-owners cannot withdraw global paymaster balance.
- **`test/TetherGuardHook.t.sol` (37/37 PASS)**
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
  - `test_MorningReview_FlagForRevert_WhenBelowFloor_StrictlyDecreases` (Penalty inversion defense)
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
  - `test_SignApproval_ExpiredGracePeriod_Reverts` (Stale approval expiration defense)
  - `test_PreCheck_SelfTargetingHook_InTier3_Reverts` (Hook self-targeting privilege escalation defense)
  - `test_Deployer_CanSetInitialPasskey_Success` (Onboarding passkey initialization)
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
- **`test/WebAuthnP256Validator.t.sol` (11/11 PASS)**
  - `test_PasskeyRegistration`
  - `test_VerifyP256Signature_NativePrecompile_Success`
  - `test_VerifyP256Signature_InvalidSignature_Fails`
  - `test_ValidateUserOp_Success`
  - `test_ValidateUserOp_EnvelopeChallengeMatch_Success` (Enforced challenge binding)
  - `test_ValidateUserOp_EnvelopeChallengeMismatch_Fails` (Replay challenge mismatch rejection)
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
- **`test/SessionKeyValidator.t.sol` (8/8 PASS)**
  - `test_SessionKeyRegistration`
  - `test_ValidateUserOp_Success`
  - `test_ValidateUserOp_WrongSigner_Fails`
  - `test_ValidateUserOp_RevokedSessionKey_Fails`
  - `test_VerifyMandateCommitment_Success` (WeIdentity W3C anchor verification)
  - `test_VerifyMandateCommitment_Mismatch_Fails` (Digest mismatch rejection)
  - `test_ERC1271_SignatureValidation`
  - `test_ERC1271_ExpiredSignature_Fails`
- **`test/TecAccount.t.sol` (7/7 PASS)**
  - `test_Initialization`
  - `test_Initialization_FrontRunning_Reverts` (Front-running takeover defense)
  - `test_Execute_WithinTetherRadius_Success`
  - `test_Execute_ExceedingTetherRadius_Reverts`
  - `test_Execute_MaliciousTargetDrain_Reverts`
  - `test_Execute_SelfTargetHook_Reverts` (Hook self-targeting defense)
  - `test_BreakingTheTether_BiometricFaceID_Success`
- **`test/VaultGasBenchmark.t.sol` (19/19 PASS - Empirical Gas & Transaction Fee Benchmarks)**
  - Measures empirical EVM gas consumption and mainnet transaction fees (20 Gwei normal, 50 Gwei congested, $2,500/ETH) across all 33 methods in `TecAccount`, `TetherGuardHook`, `SessionKeyValidator`, and `TecPaymaster`.

---

## 5. Empirical Multi-Chain Transaction Fee & Gas Economics

### 📡 Live Network Gas Benchmarks
Live base fees captured directly from official block explorers:
* **Ethereum Mainnet ([Etherscan Gas Tracker](https://etherscan.io/gastracker)):** `0.092 Gwei` (Base: `0.092 Gwei` | Priority: `0.001 Gwei`)
* **Base Layer 2 ([BaseScan Gas Tracker](https://basescan.org/gastracker#gassender)):** `0.005 Gwei`
* **Reference ETH Price:** `$2,500 USD`

---

### 📊 Operational Transaction Fee Matrix: Ethereum Mainnet vs. Base L2

The table below profiles the **primary operational methods used across the card lifecycle**, documenting exact EVM gas consumption alongside real-world execution costs on **Ethereum Mainnet** and **Base L2**:

| Method & Contract | Operational Trigger ("When Will It Be Used?") | Gas Used | Ethereum L1 (0.092 Gwei)<br/>Fee (ETH) \| USD | Base L2 (0.005 Gwei)<br/>Fee (ETH) \| USD |
| :--- | :--- | :---: | :---: | :---: |
| **`TecAccount.execute`**<br/>*(USDC Transfer)* | AI Agent or cardholder executes a bounded vendor invoice or merchant payment in USDC under the Tether Radius. | **168,554** | 0.0000155 ETH<br/>**$0.0388 (3.9¢)** | 0.0000008 ETH<br/>**$0.0021 (0.2¢)** |
| **`TecAccount.execute`**<br/>*(Lido ETH Stake)* | Autonomous AI rebalances idle corporate treasury into staking yields (Lido stETH) within discretionary limits. | **185,326** | 0.0000171 ETH<br/>**$0.0426 (4.3¢)** | 0.0000009 ETH<br/>**$0.0023 (0.2¢)** |
| **`TecAccount.executeFromExecutor`**<br/>*(AI UserOp)* | Authorized LangGraph AI session execution module submits autonomous batched operations on behalf of the vault. | **296,175** | 0.0000273 ETH<br/>**$0.0681 (6.8¢)** | 0.0000015 ETH<br/>**$0.0037 (0.4¢)** |
| **`SessionKeyValidator.validateUserOp`**<br/>*(Mandate Validation)* | ERC-4337 EntryPoint verifies ephemeral AI session key signature and WeIdentity mandate root before UserOp execution. | **14,976** | 0.0000014 ETH<br/>**$0.0034 (0.3¢)** | 0.0000001 ETH<br/>**$0.0002 (0.02¢)** |
| **`TetherGuardHook.completeBiometricVerificationWithP256`** | Breaking the Tether: Cardholder authenticates via hardware FaceID/Passkey (RIP-7212), opening a 5-minute grace window. | **103,946** | 0.0000096 ETH<br/>**$0.0239 (2.4¢)** | 0.0000005 ETH<br/>**$0.0013 (0.1¢)** |
| **`TetherGuardHook.submitSignApproval`**<br/>*(Direct Accept/Reject)* | User confirms or rejects a breakout transaction proposed by the AI Brain within the active 5-minute biometric window. | **78,845** | 0.0000073 ETH<br/>**$0.0181 (1.8¢)** | 0.0000004 ETH<br/>**$0.0010 (0.1¢)** |
| **`TetherGuardHook.submitSignApprovalWithSignature`**<br/>*(Gasless Relay)* | Cardholder signs off-chain EIP-712 approval; application bundler/relayer submits on-chain for 100% gasless user UX. | **70,637** | 0.0000065 ETH<br/>**$0.0162 (1.6¢)** | 0.0000004 ETH<br/>**$0.0009 (0.09¢)** |
| **`TetherGuardHook.ratifyTransaction`**<br/>*(Morning Review 👍)* | Morning Review: User ratifies overnight autonomous AI trades, replenishing the spending radius and accumulating trust. | **85,809** | 0.0000079 ETH<br/>**$0.0197 (2.0¢)** | 0.0000004 ETH<br/>**$0.0011 (0.1¢)** |
| **`TetherGuardHook.flagTransactionForRevert`**<br/>*(Morning Review 👎)* | Morning Review: User objects to an overnight trade, flagging it for unwind and penalizing the AI Brain's radius by 20%. | **88,628** | 0.0000082 ETH<br/>**$0.0204 (2.0¢)** | 0.0000004 ETH<br/>**$0.0011 (0.1¢)** |
| **`TetherGuardHook.submitTransactionNote`**<br/>*(Operator Feedback)* | Cardholder logs supervisory guidance/notes to educate the AI Brain on future corporate expense preferences. | **78,357** | 0.0000072 ETH<br/>**$0.0180 (1.8¢)** | 0.0000004 ETH<br/>**$0.0010 (0.1¢)** |
| **`TetherGuardHook.calibrateDynamicRadius`**<br/>*(Vault 10% Elasticity)* | Vault autonomously recalculates and increases AI daily spending limit by up to 10% after 24h consecutive ratifications. | **64,791** | 0.0000060 ETH<br/>**$0.0149 (1.5¢)** | 0.0000003 ETH<br/>**$0.0008 (0.08¢)** |
| **`TetherGuardHook.recordAIHeartbeat`**<br/>*(Liveness Ping)* | AI agent periodically pings the vault to prevent the 48-hour Inactive AI Heartbeat watchdog timeout from tripping. | **48,601** | 0.0000045 ETH<br/>**$0.0112 (1.1¢)** | 0.0000002 ETH<br/>**$0.0006 (0.06¢)** |
| **`TetherGuardHook.triggerDeadmanRecovery`**<br/>*(Guardian Recovery)* | Designated corporate guardian reclaims custody after 90 days of cardholder inactivity (emergency/medical recovery). | **39,885** | 0.0000037 ETH<br/>**$0.0092 (0.9¢)** | 0.0000002 ETH<br/>**$0.0005 (0.05¢)** |
| **`TecPaymaster.validatePaymasterUserOp`**<br/>*(Anti-Grief Check)* | EntryPoint checks that cumulative AI session gas sponsorship does not breach the strict 0.005 ETH anti-griefing budget. | **9,103** | 0.0000008 ETH<br/>**$0.0021 (0.2¢)** | 0.0000001 ETH<br/>**$0.0001 (0.01¢)** |
| **`TecPaymaster.postOp`**<br/>*(Gas Metering & Escrow Debit)* | EntryPoint reconciles actual execution gas consumed and debits the corporate sponsor's prepaid gas escrow deposit. | **64,843** | 0.0000060 ETH<br/>**$0.0149 (1.5¢)** | 0.0000003 ETH<br/>**$0.0008 (0.08¢)** |
| **`TecAccount.initialize`**<br/>*(Vault Onboarding Setup)* | One-time vault initialization binding the Passkey root owner, TetherGuardHook policy, and SessionKeyValidator. | **98,785** | 0.0000091 ETH<br/>**$0.0227 (2.3¢)** | 0.0000005 ETH<br/>**$0.0012 (0.1¢)** |

---

### 💡 Multi-Chain Economic Analysis & Takeaways:
1. **Ethereum Mainnet Cost Realities:** At current live network conditions (`0.092 Gwei`), all core operations cost **between $0.002 and $0.068 (a fraction of a cent to ~6.8 cents)**.
2. **Base Layer 2 Hyper-Efficiency:** Deploying on Base L2 (`0.005 Gwei`) provides an **18.4x fee discount**, reducing every operation to **sub-cent costs ($0.0001 to $0.0037)**.
3. **Consortium Chains (WeBank / FISCO BCOS):** On consortium chains, native enterprise gas quota sponsorship enables **100% free ($0.00) cardholder operations**.
4. **Anti-Griefing Safety:** The `0.005 ETH` session paymaster cap covers **>180 autonomous userOps on Mainnet** and **>3,300 userOps on Base L2**, completely eliminating prompt-injection treasury draining risks.

---

## 6. Deployment & Shared Handoff

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

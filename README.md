# Tec-C (Tethered Expense Corporate Card)
### Autonomous On-Chain Agent Wallet with Mathematical Security Invariants

[![Solidity](https://img.shields.io/badge/Solidity-0.8.24-363636?logo=solidity)](https://soliditylang.org/)
[![Foundry](https://img.shields.io/badge/Foundry-156%2F156%20Passing-brightgreen?logo=ethereum)](https://getfoundry.sh/)
[![ERC-7579](https://img.shields.io/badge/ERC--7579-Modular%20Account-blue)](https://erc7579.com/)
[![ERC-4337](https://img.shields.io/badge/ERC--4337-Account%20Abstraction-purple)](https://eips.ethereum.org/EIPS/eip-4337)
[![RIP-7212](https://img.shields.io/badge/RIP--7212-P256%20Precompile%20%40%200x100-orange)](https://github.com/ethereum/RIPs/blob/master/RIPS/rip-7212.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 🏆 FinTechathon 2026 Overview
- **Competition:** Shenzhen International FinTech Competition (FinTechathon 2026) — International Track
- **Topic:** **Topic F — Agent Wallet (Autonomous On-Chain Wallet)**
- **Co-Hosts:** **Tsinghua University PBCSF** & **WeBank**
- **Repository:** [`https://github.com/AhmedFouad15/TEC-C`](https://github.com/AhmedFouad15/TEC-C)

---

## 📑 Repository Structure

```
TEC-C/
├── contracts/                               # Smart Contracts Layer (Foundry)
│   ├── src/                                 # Production Smart Contracts (100% NatSpec)
│   │   ├── TecAccount.sol                   # ERC-7579 Modular Smart Account
│   │   ├── hooks/
│   │   │   └── TetherGuardHook.sol          # Dual-Axis Policy Hook & Invariant Engine
│   │   ├── validators/
│   │   │   ├── SessionKeyValidator.sol      # EIP-712 AI Agent Mandate Validator
│   │   │   └── WebAuthnP256Validator.sol    # RIP-7212 / Passkey FaceID Validator
│   │   ├── paymaster/
│   │   │   └── TecPaymaster.sol             # ERC-4337 Gas Sponsorship & Anti-Griefing
│   │   └── interfaces/                      # Standard ERC & Chainlink Interfaces
│   ├── test/                                # 12 Test Suites (156 passing tests)
│   │   ├── DeadmanAndHeartbeat.t.sol        # Watchdog & recovery tests
│   │   ├── MultiTokenTether.t.sol           # Chainlink USD oracle normalization
│   │   ├── SessionKeyValidator.t.sol        # Session key mandate verification
│   │   ├── TecAccount.t.sol                 # Account initialization & hook delegation
│   │   ├── TecPaymaster.t.sol               # Sponsorship limits & gas griefing
│   │   ├── TetherGuardHook.t.sol            # Velocity limits & morning review
│   │   ├── VaultComprehensiveFuzz.t.sol     # Invariant property fuzzing (256 runs)
│   │   ├── VaultEdgeCases.t.sol             # Boundary condition & zero-value tests
│   │   ├── VaultGasBenchmark.t.sol          # Multi-chain empirical gas matrix
│   │   ├── VaultLifecycleScenarios.t.sol    # Multi-day enterprise lifecycle
│   │   ├── VaultSecurityHardening.t.sol     # SEC-01..08 security regression tests
│   │   └── WebAuthnP256Validator.t.sol      # P-256 precompile signature tests
│    ├── script/
│   │   ├── DeployTecC.s.sol                 # Foundry deployment script
│   │   └── export_shared_artifacts.py       # Contract ABI & artifact exporter
│   ├── foundry.toml                         # Compiler & optimizer configuration
│   └── README.md                            # Smart contracts deep dive
├── shared/
│   └── contracts.json                       # Exported ABIs and bytecode for frontend/AI
├── Tec-C_Vault_User_and_Architecture_Guide.pdf # 8-page comprehensive whitepaper guide
├── Tec-C_4_Person_Execution_Roadmap.pdf     # Team milestone & operational breakdown
├── Tec-c_Plain_English_Guide.pdf            # Plain English user manual
├── project.pdf                              # Original architecture blueprint
├── excution.pdf                             # System execution specification
├── .github/workflows/ci.yml                 # Root GitHub Actions CI workflow
├── .gitignore                               # Git ignore configuration
├── LICENSE                                  # MIT License
└── README.md                                # Root repository guide (this file)
```

---

## 🏛️ System Architecture

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

## 🛡️ Core Security Invariants

### 1. 🏛️ Vault Sovereignty (Never Penalize or Freeze the Vault)
- **No On-Chain Halts from News Sentiment:** Halting or freezing an on-chain Vault based on off-chain news sentiment causes catastrophic liquidation cascades. Therefore, all NLP news sentiment models belong **exclusively in the off-chain AI Cognitive Brain**.
- **Never Penalize the Vault:** Penalties apply strictly and exclusively to the **AI Brain's autonomous discretionary session quota** (`penalizeBrain`). When a user objects or penalizes a transaction during morning review, the AI Brain's autonomous Tether Radius is throttled (`tetherRadius - 10%`), but the Vault treasury, user balance, and FaceID root owner capabilities remain 100% unconstrained.

### 2. 🛡️ Independent Vault Calibration (Max 10% Daily Growth Cap)
- Dynamic limit adjustments are computed **autonomously on-chain by the Vault** via `calibrateDynamicRadius(address account)`:
  $$\text{New Radius} = \min\left(\text{Current Radius} \times 1.10,\, \text{Max Elastic Ceiling}\right)$$
- The autonomous AI Brain cannot propose its own budget increases, guaranteeing mathematically bounded growth of at most **10% per 24 hours**.

### 3. 🔐 Breaking the Tether Protocol (5-Minute Biometric Window & Sign Approval)
- **Active Biometric Guard (No Indefinite Session Bypass):**
- Simply having an active session does NOT grant an automatic, indefinite bypass.
- When an execution exceeds the daily Tether Radius or interacts with higher-tier protocols:
  1. **Biometric Challenge**: User completes biometric verification (FaceID / TouchID / Passkey).
  2. **5-Minute Grace Period**: Successful verification opens an on-chain 5-minute active window (`BIOMETRIC_VERIFICATION_WINDOW = 5 minutes`).
  3. **Subsequent Brain Transactions**: The user is **NOT** prompted for biometrics again; instead, the user provides a simple **Sign Approval** (**Accept** or **Reject**).
  4. **Expiry**: Once 5 minutes elapse, any further breakout requires fresh biometric re-verification.

### 4. 💓 Inactive AI Heartbeat & Corporate Dead-Man's Switch
- **Inactive AI Heartbeat Watchdog (48h Timeout):** The AI session key must regularly broadcast an on-chain heartbeat via `recordAIHeartbeat(account)`. If $>48\text{ hours}$ elapse without an AI heartbeat, autonomous execution reverts (`AIHeartbeatStale`).
- **Corporate Dead-Man's Switch (90d Timeout):** If the primary user is inactive for $>90\text{ days}$, a designated corporate guardian can trigger recovery via `triggerDeadmanRecovery(account, newOwner)`, transferring custody to a corporate successor.

### 5. 🌐 Dual-Axis Risk Engine
- **Axis 1 (Asset Universe):**
  - **Tier 1 (Core Capital Preservation):** Mega-cap assets (BTC, ETH), fiat stablecoins (USDC, USDT, e-CNY), tokenized commodities (PAXG Gold), and money-market instruments (Shibor MMF).
  - **Tier 2 (Dynamic Growth & Active DeFi):** Liquid staking (stETH, rETH), AMM liquidity pools (Uniswap, Curve), and yield vaults (Aave).
  - **Tier 3 (Omni-Universe / Unrestricted):** Zero whitelist restriction, strictly bound by Tether Radius velocity limits and biometric breakout authentication.
- **Axis 2 (The Tether Radius & Dynamic Elasticity):**
  - Initial baseline radius configured at onboarding (10%, 25%, 50%, 100%, or Custom).
  - Static Mode vs. Adaptive Learning Mode with hard elastic ceiling (`maxElasticCeiling`).

### 6. ☀️ Asynchronous Morning Review System
Overnight autonomous trades are recorded on-chain as `PENDING_REVIEW`:
1. **👍 Like / Ratify (`ratifyTransaction`):** Replenishes the daily spending allowance and increments on-chain `consecutiveRatifications`.
2. **👎 Revert / Object (`flagTransactionForRevert`):** Flags transaction for cognitive unwind and applies a 20% trust penalty to the AI Brain's radius.
3. **📝 Note / Educate (`submitTransactionNote`):** Logs semantic educational notes to the AI Brain, with an optional 10% penalty to the Brain's discretionary quota (`penalizeBrain = true`).

### 7. 🪙 Multi-Token & ERC-20 Tether Radius Inspection (Chainlink USD Normalized)
- **Values are NEVER hardcoded in ETH.**
- `TetherGuardHook` dynamically unpacks inner calldata to inspect ERC-20 method calls (`transfer`, `approve`, `transferFrom`).
- Normalizes token amounts to 8-decimal USD via Chainlink Price Feeds (`latestRoundData`).
- Multiple token transfers accumulate against the same daily USD spending radius.
- Enforces strict oracle freshness ($< 24\text{ hours}$) and non-negative answer guards (`InvalidOraclePrice`, `StaleOraclePrice`).

---

## ⚡ Multi-Chain Gas Economics Matrix

Empirical transaction fee benchmarks computed from the on-chain test suite and evaluated across live block explorer gas trackers:

| Operation | Method Name | Gas (Units) | Ethereum Mainnet (0.092 Gwei, ETH=$2500) | Base L2 (0.005 Gwei, 18.4x discount) | WeBank / FISCO BCOS | When Will It Be Used? |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Passkey Reg.** | `setAccountPasskey` | 14,464 | **$0.0033** | **$0.00018** | **$0.00** | Initial account onboarding |
| **P-256 Verif.** | `verifyP256Signature` | 9,964 | **$0.0023** | **$0.00012** | **$0.00** | Hardware passkey verification |
| **Session Reg.** | `setSessionKey` | 21,639 | **$0.0050** | **$0.00027** | **$0.00** | AI session key provisioning |
| **Mandate Verif.** | `verifyMandate` | 16,701 | **$0.0038** | **$0.00021** | **$0.00** | Session key cryptographic mandate check |
| **Policy Init.** | `initializeAccountPolicy`| 30,925 | **$0.0071** | **$0.00039** | **$0.00** | Initial risk tier & radius configuration |
| **Autonomous Step**| `autonomousAdjustment` | 287,736 | **$0.0662** | **$0.00360** | **$0.00** | Autonomous AI velocity radius step-up |
| **Vault Calib.** | `calibrateDynamicRadius`| 236,292 | **$0.0543** | **$0.00295** | **$0.00** | Vault-native 24h calibration (+10% cap) |
| **Biometric Win.** | `completeBiometric` | 123,913 | **$0.0285** | **$0.00155** | **$0.00** | 5-minute biometric breakout window |
| **Sign Approval** | `submitSignApproval` | 254,632 | **$0.0586** | **$0.00318** | **$0.00** | User Accept/Reject for proposed trade |
| **Gasless Sign** | `submitWithSignature` | 298,887 | **$0.0687** | **$0.00374** | **$0.00** | Gasless relayer signature approval |
| **AI Heartbeat** | `recordAIHeartbeat` | 75,868 | **$0.0175** | **$0.00095** | **$0.00** | AI agent 48h liveness broadcast |
| **Heartbeat Conf.**| `configureHeartbeat` | 37,236 | **$0.0086** | **$0.00047** | **$0.00** | Custom watchdog timeout adjustment |
| **Deadman Conf.** | `configureDeadman` | 137,694 | **$0.0317** | **$0.00172** | **$0.00** | Corporate recovery guardian registration |
| **Deadman Trigger**| `triggerDeadman` | 193,692 | **$0.0445** | **$0.00242** | **$0.00** | 90-day inactivity custody rotation |
| **User Activity** | `pingUserActivity` | 192,390 | **$0.0442** | **$0.00240** | **$0.00** | Dead-man timer reset via app engagement |
| **Feed Override** | `setAccountPriceFeed` | 433,748 | **$0.0998** | **$0.00542** | **$0.00** | Custom Chainlink token oracle mapping |

> **Key Takeaway:** At live Etherscan gas rates (`0.092 Gwei`), all core operations cost **a fraction of a cent to ~6.8 cents** on Ethereum Mainnet. On Base L2 (`0.005 Gwei`), all operations are sub-cent (**$0.0001 to $0.0037**). On WeBank / FISCO BCOS consortium chains, transactions are **100% free ($0.00)** via enterprise gas quota sponsorship.

---

## 🧪 Test Verification & Coverage

Tec-C features 100% green tests across **12 Foundry suites** containing **156 tests**:

```bash
Ran 12 test suites in 1.29s (8.29s CPU time): 156 tests passed, 0 failed, 0 skipped (156 total tests)
```

### Test Breakdown by Suite
1. `DeadmanAndHeartbeatTest`: 10 passed
2. `SessionKeyValidatorTest`: 8 passed
3. `TecPaymasterTest`: 6 passed
4. `TecAccountTest`: 7 passed
5. `MultiTokenTetherTest`: 12 passed
6. `VaultComprehensiveFuzzTest`: 5 passed (256 fuzz runs each)
7. `VaultLifecycleScenariosTest`: 4 passed (multi-day enterprise lifecycles)
8. `TetherGuardHookTest`: 37 passed
9. `VaultEdgeCasesTest`: 19 passed
10. `VaultSecurityHardeningTest`: 18 passed (SEC-01..08 regressions)
11. `WebAuthnP256ValidatorTest`: 11 passed (RIP-7212 precompile calls)
12. `VaultGasBenchmarkTest`: 19 passed (empirical multi-chain benchmarks)

---

## 🚀 Quickstart & Building

### Prerequisites
- [Foundry](https://getfoundry.sh/) (`forge`, `cast`, `anvil`)

### Compile Contracts
```bash
cd contracts
forge build
```

### Run All 156 Tests
```bash
forge test
```

### Check Bytecode Sizes (EIP-170 Compliance)
```bash
forge build --sizes
```

### Check Code Formatting
```bash
forge fmt --check
```

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).

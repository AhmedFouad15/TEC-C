# Tec-C (Tethered Expense Corporate Card)
### Autonomous On-Chain Agent Wallet with Mathematical Security Invariants

[![Solidity](https://img.shields.io/badge/Solidity-0.8.24-363636?logo=solidity)](https://soliditylang.org/)
[![Foundry](https://img.shields.io/badge/Foundry-167%2F167%20Passing-brightgreen?logo=ethereum)](https://getfoundry.sh/)
[![Python Brain](https://img.shields.io/badge/Python%20Brain-594%2F594%20Passing-blue?logo=python)](https://fastapi.tiangolo.com/)
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
├── agent/                                   # Off-Chain AI Brain & Execution Engines
│   ├── tecc_brain/
│   │   ├── api/                             # FastAPI Endpoints (Mandate, Risk, Profile, Arbitrage, Biometrics)
│   │   ├── biometrics/                      # WebAuthn NIST P-256 Passkey Biometric Engine
│   │   ├── pegguard/                        # Autonomous 25-Asset Scanner & Stateful Watermark Memory
│   │   ├── virtual_session/                 # Remote Phone Access Gateway & Cloudflare Quick-Tunnel
│   │   ├── graph/                           # LangGraph AI Cognitive Planner & Intent Pipeline
│   │   ├── sentinel/                        # Fear & Greed, Grok, and Multi-Oracle Sentiment
│   │   ├── strategy/                        # Autonomous Playbooks & Portfolio Risk Engine
│   │   └── app.py                           # FastAPI Application Entrypoint (Port 8000)
│   └── tests/                               # 594 Unit, Property & Integration Tests (100% Passing)
├── contracts/                               # Smart Contracts Layer (Foundry)
│   ├── src/                                 # Production Smart Contracts (100% NatSpec)
│   │   ├── TecAccount.sol                   # ERC-7579 Modular Smart Account
│   │   ├── hooks/
│   │   │   └── TetherGuardHook.sol          # Dual-Axis Policy Hook & Invariant Engine
│   │   ├── validators/
│   │   │   ├── P256Verifier.sol             # RIP-7212 0x100 + Pure-Solidity P-256 Curve Fallback
│   │   │   ├── SessionKeyValidator.sol      # EIP-712 AI Agent Mandate Validator
│   │   │   └── WebAuthnP256Validator.sol    # Hardware Passkey / Biometric Validator
│   │   ├── paymaster/
│   │   │   └── TecPaymaster.sol             # ERC-4337 Gas Sponsorship & Anti-Griefing
│   │   └── interfaces/                      # Standard ERC & Chainlink Interfaces
│   ├── test/                                # 13 Foundry Test Suites (167 passing tests)
│   │   ├── WebAuthnP256Validator.t.sol      # RIP-7212, Pure-Solidity Fallback, Low-S, UV & Recovery
│   │   ├── TetherGuardHook.t.sol            # Velocity limits & morning review
│   │   ├── CrossChainTetherTest.t.sol       # Multi-chain state lock & par-repo facility
│   │   ├── VaultComprehensiveFuzz.t.sol     # Invariant property fuzzing (256 runs)
│   │   └── ...                              # All 13 contract test suites
│   ├── foundry.toml                         # Compiler & optimizer configuration
│   └── README.md                            # Smart contracts deep dive
├── shared/
│   ├── api_spec.json                        # Exported OpenAPI 3.1 specification (35 endpoints)
│   └── contracts.json                       # Exported ABIs and bytecode for frontend/AI
├── Virtual_Session_Design.pdf               # Remote phone access design & security model
├── Tec-C_Vault_User_and_Architecture_Guide.pdf # 8-page comprehensive whitepaper guide
├── Tec-C_4_Person_Execution_Roadmap.pdf     # Team milestone & operational breakdown
├── Tec-c_Plain_English_Guide.pdf            # Plain English user manual
├── project.pdf                              # Original architecture blueprint
├── excution.pdf                             # System execution specification
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

## 🧪 Test Verification & Coverage (761 Passing Tests)

Tec-C features **761 automated tests** across Foundry smart contracts and the Python AI Brain / Virtual Session suites:

### 1. Smart Contracts Layer: 167 / 167 Passing Tests
```bash
Ran 13 test suites in 879.37ms (6.52s CPU time): 167 tests passed, 0 failed, 0 skipped (167 total tests)
```
- `WebAuthnP256ValidatorTest`: 15 passed (RIP-7212 precompile `0x100`, L1/FISCO pure-Solidity NIST P-256 fallback, low-$s$ malleability protection, UV flag assertion, multi-device passkeys, and guardian recovery)
- `TetherGuardHookTest`: 37 passed (Dynamic elasticity, breaking the tether, morning reviews)
- `MultiTokenTetherTest`: 12 passed (Chainlink USD normalization)
- `TecAccountTest`: 7 passed (ERC-7579 modular account execution)
- `TecPaymasterTest`: 6 passed (Gas sponsorship & anti-griefing)
- `CrossChainTetherTest`: 7 passed (Multi-chain state lock & FISCO BCOS par-repo facility)
- `DeadmanAndHeartbeatTest`: 10 passed (AI heartbeat watchdog & 90-day deadman switch)
- `VaultComprehensiveFuzzTest`: 5 passed (256 fuzz runs each)
- `VaultSecurityHardeningTest`: 18 passed (SEC-01..08 security regression invariants)
- `VaultEdgeCasesTest`: 19 passed (Zero-value & boundary conditions)
- `VaultLifecycleScenariosTest`: 4 passed (Multi-day enterprise lifecycles)
- `SessionKeyValidatorTest`: 8 passed (EIP-712 AI mandate verification)
- `VaultGasBenchmarkTest`: 19 passed (Multi-chain empirical gas matrix)

### 2. Python AI Brain & Virtual Session Layer: 594 / 594 Passing Tests
```bash
594 passed, 11 warnings in 31.27s (100% passing)
```
- `test_virtual_session.py`: 10 passed (Cloudflare Quick-Tunnel, WebAuthn Face ID pairing, laptop approval, step-up tokens, and route isolation)
- `test_pegguard.py`: 18 passed (Autonomous 25-asset catalog, depeg scanner, stateful unprofitable-price watermark memory)
- `test_biometrics.py`: 15 passed (NIST P-256 signing, low-$s$ normalization, UP/UV authenticatorData parser, guardian recovery)
- `test_pipeline.py`, `test_brain.py`, `test_planner.py`: Cognitive intent parser, firewall sieve, and risk engine

---

## ⚡ Autonomous PegGuard Depeg Scanner & Memory
- **25 Assets Across 4 Classes**:
  1. *Fiat-Backed & Decentralized Stablecoins (Class B — Par-Pegged)*: USDC, USDT, DAI, USDe, PYUSD, EURC, GHO, crvUSD.
  2. *Liquid Staking Tokens (LSTs — Yield-Accruing / Fair-Value Ratio)*: stETH, wstETH, rETH, cbETH.
  3. *Liquid Restaking Tokens (LRTs — Class A Restaked)*: weETH, ezETH, rsETH, eETH.
  4. *Wrapped, Bridged & Synthetic Pegged Assets (Class C)*: WBTC, cbBTC, tBTC, WETH, ARB, wstUSR, USDS, sUSDe, sDAI.
- **Stateful Watermark Memory**: Remembers unprofitable depeg prices per asset so the engine never wastes gas checking the same unprofitable trade repeatedly; scans again only when price diverges further below the recorded watermark.

---

## 🛡️ Decentralized Biometrics & 4 Production Nuances
- **RIP-7212 Precompile (`0x100`) + Pure-Solidity Fallback**:
  - Automatically queries native precompile `0x100` on Arbitrum One, Optimism, Polygon, and Base (~3.4k gas).
  - Falls back to pure-Solidity NIST P-256 Jacobian projective coordinate verification via EIP-198 `modexp` (`0x05`) on Ethereum L1 Mainnet and FISCO BCOS nodes.
- **Signature Malleability Defense**: Strictly enforces $0 < s \le n/2$ to prevent UserOp signature replay.
- **W3C `authenticatorData` Flags**: Asserts Bit 0 (`UP = 0x01`, User Present) and Bit 2 (`UV = 0x04`, User Verified) to ensure biometric FaceID/TouchID was verified.
- **Multi-Device Passkeys & Emergency Guardian**: Allows registering multiple passkeys per account with an emergency guardian recovery mechanism.

---

## 📱 Virtual Session: Remote Phone Access
- **Two Separate Servers**:
  - *Admin App (`127.0.0.1:8000`, Never Tunneled)*: Local management, session creation, pairing approvals, API keys, and audit logs.
  - *Mobile Gateway (`127.0.0.1:8001`, Tunneled)*: Tunneled via Cloudflare quick-tunnel (`https://xxxx.trycloudflare.co`). Exposes only allow-listed routes; returns 404 for any internal or admin endpoint.
- **Biometric Passkey Pairing**: 6-digit confirmation code displayed on phone and approved on laptop.
- **Action-Bound Step-Up Biometrics**: Sensitive trade actions require a 60-second single-use `HMAC(server_secret, action_hash || nonce)` step-up token.
- **Kill Switch**: Instant one-click revocation of all active sessions and tunnel termination.

---

## 🚀 Quickstart & Building

### Prerequisites
- [Foundry](https://getfoundry.sh/) (`forge`, `cast`, `anvil`)
- Python 3.10+ / 3.11+

### Run Smart Contract Tests (167 Tests)
```bash
cd contracts
forge test
```

### Run Python AI Brain & Virtual Session Tests (594 Tests)
```bash
cd agent
python -m pytest -q
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

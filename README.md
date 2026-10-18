# Tec-C (Tethered Expense Corporate Card)
### Autonomous On-Chain Agent Wallet with Mathematical Security Invariants

[![Solidity](https://img.shields.io/badge/Solidity-0.8.24-363636?logo=solidity)](https://soliditylang.org/)
[![Foundry](https://img.shields.io/badge/Foundry-170%2F170%20Passing-brightgreen?logo=ethereum)](https://getfoundry.sh/)
[![Python Brain](https://img.shields.io/badge/Python%20Brain-622%2F622%20Passing-blue?logo=python)](https://fastapi.tiangolo.com/)
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

## 📚 Complete Technical Documentation Index

Detailed architectural breakdowns, run guides, and econometric specifications are available in the dedicated [`docs/`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs) folder:

| Guide | Subject | Description |
|---|---|---|
| [`01_SYSTEM_ARCHITECTURE.md`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/01_SYSTEM_ARCHITECTURE.md) | Multi-Agent Design | 3-Member execution model, LangGraph cognitive state machine, and dual-server IPC |
| [`02_PREREQUISITES_AND_RUN_GUIDE.md`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/02_PREREQUISITES_AND_RUN_GUIDE.md) | Run & Deploy Manual | Step-by-step setup (Python, Foundry, WSL 2), test execution, and deployment commands |
| [`03_MARKET_DATA_FEEDS_AND_APIS.md`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/03_MARKET_DATA_FEEDS_AND_APIS.md) | Feeds & Free Alternatives | $0.00 zero-cost design, free public endpoints, and enterprise feed comparative matrix |
| [`04_MULTICHAIN_AND_FISCO_BCOS_CLUSTER.md`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/04_MULTICHAIN_AND_FISCO_BCOS_CLUSTER.md) | Multi-Chain & Node Cluster | FISCO BCOS testnet cluster setup, millisecond EVM nuance, and auto-supervisor |
| [`05_FAIL_CLOSED_STRICTNESS_HIERARCHY.md`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/05_FAIL_CLOSED_STRICTNESS_HIERARCHY.md) | Math > AI Hierarchy | Tsinghua academic formulation, asymmetric bounding proofs ($B_{AI} \le B_{math}$), and timeouts |
| [`06_PRIVACY_AUDIT_ANCHORS_AND_SLIPPAGE_RESILIENCE.md`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/06_PRIVACY_AUDIT_ANCHORS_AND_SLIPPAGE_RESILIENCE.md) | Audit & Slippage Engine | SHA-256 anchors on FISCO BCOS, orderbook thinning recovery ($Q^*/2$), and positive carry |
| [`07_DEFI_PROTOCOLS_AND_ROUTING.md`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/07_DEFI_PROTOCOLS_AND_ROUTING.md) | Protocol Registry | Verified contracts, ABIs, function selectors, and risk tiers (Lido, Aave, Curve, Uniswap) |

---

## 📑 Repository Structure

```
TEC-C/
├── agent/                                   # Off-Chain AI Brain & Execution Engines
│   ├── tecc_brain/
│   │   ├── api/                             # FastAPI Endpoints (Mandate, Risk, Profile, Arbitrage, Biometrics)
│   │   ├── biometrics/                      # WebAuthn NIST P-256 Passkey Biometric Engine
│   │   ├── graph/                           # LangGraph Multi-Agent Cognitive Pipeline & Intent Sieve
│   │   ├── market/                          # Live Market Data Feeds & Free Alternative Catalogs
│   │   ├── onchain/                         # Multi-Chain Executors, Relayers, Oracles & FISCO Node Supervisor
│   │   ├── pegguard/                        # Autonomous 25-Asset Scanner & Stateful Watermark Memory
│   │   ├── sentinel/                        # Fear & Greed, Grok, and Multi-Oracle Sentiment
│   │   ├── strategy/                        # Autonomous Playbooks & Portfolio Risk Engine
│   │   ├── virtual_session/                 # Remote Phone Access Gateway & Cloudflare Quick-Tunnel
│   │   └── app.py                           # FastAPI Application Entrypoint (Port 8000)
│   └── tests/                               # 622 Unit, Property & Integration Tests (100% Passing)
├── contracts/                               # Smart Contracts Layer (Foundry)
│   ├── src/                                 # Production Smart Contracts (100% NatSpec)
│   │   ├── TecAccount.sol                   # ERC-7579 Modular Smart Account
│   │   ├── audit/
│   │   │   └── PrivacyAuditAnchor.sol       # Cryptographic Audit Anchor on FISCO BCOS
│   │   ├── hooks/
│   │   │   └── TetherGuardHook.sol          # Dual-Axis Policy Hook & Invariant Engine
│   │   ├── validators/
│   │   │   ├── P256Verifier.sol             # RIP-7212 0x100 + Pure-Solidity P-256 Curve Fallback
│   │   │   ├── SessionKeyValidator.sol      # EIP-712 AI Agent Mandate Validator
│   │   │   └── WebAuthnP256Validator.sol    # Hardware Passkey / Biometric Validator
│   │   ├── paymaster/
│   │   │   └── TecPaymaster.sol             # ERC-4337 Gas Sponsorship & Anti-Griefing
│   │   └── interfaces/                      # Standard ERC & Chainlink Interfaces
│   ├── test/                                # 14 Foundry Test Suites (170 passing tests)
│   ├── foundry.toml                         # Compiler & optimizer configuration
│   └── README.md                            # Smart contracts deep dive
├── docs/                                    # Comprehensive Technical & Architectural Documentation
├── shared/
│   ├── api_spec.json                        # Exported OpenAPI 3.1 specification (35 endpoints)
│   ├── chainlink_feeds.json                 # Verified Chainlink Oracle Registry (Multi-Chain)
│   ├── contracts.arbitrum.json              # Deployed addresses on Arbitrum One
│   ├── contracts.fisco.json                 # Deployed addresses on FISCO BCOS (Chain ID 20200)
│   ├── contracts.sepolia.json               # Deployed addresses on Ethereum Sepolia
│   └── defi_protocols.json                  # Verified DeFi Protocol Registry & Function Selectors
├── Virtual_Session_Design.pdf               # Remote phone access design & security model
├── Tec-C_Vault_User_and_Architecture_Guide.pdf # Comprehensive whitepaper guide
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
│                 │ (Root Signer)                            │ (Session Signer)   │
│                 ▼                                          ▼                    │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                    SessionKeyValidator (ERC-7579)                       │   │
│   │  - Validates EIP-712 UserMandate commitments                            │   │
│   │  - Verifies 117-byte ECDSA session signatures via ERC-1271              │   │
│   │  - Enforces validity time bounds & mandate policy merkle root           │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│                                        ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                       TecAccount (ERC-7579 Core)                        │   │
│   │  - Modular ERC-4337 Smart Account with pre/post execution hooks         │   │
│   │  - Zero funds movable without active TetherGuardHook authorization      │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│                                        ▼                                        │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                     TetherGuardHook (ERC-7579 Hook)                     │   │
│   │  - Dual-Axis Spending Limit: Meters daily cumulative spend in USD       │   │
│   │  - Dynamic Elasticity: Ratified safe transactions expand radius by 10%  │   │
│   │  - Breaking the Tether: Biometric FaceID required to exceed radius      │   │
│   │  - Whitelist & Risk Tier Enforcement (Tier 1 Core, Tier 2 Growth)       │   │
│   │  - Deadman Switch & AI Heartbeat Watchdog (<48h ping required)          │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔬 Core Innovations & Theoretical Breakthroughs

### 1. Fail-Closed Strictness Hierarchy: Math > AI (from WeBank-AI)
- **Tsinghua Academic Foundation (Prof. Dacheng Xiu & Prof. Wolfgang Härdle)**:
  LLMs and sentiment models can hallucinate, lag, or time out during high-volatility flash crashes.
- **Strict Invariant Enforcement**:
  - The AI Brain can only strictly **tighten** constraints ($B_{AI} \le B_{math}$), never loosen them.
  - The AI can veto a candidate, reduce allocation size, or require biometric verification.
  - The AI can **never** override a quantitative Layer 1–5 rejection or expand authorization.
  - If the model or sentiment API lags ($> 8.0\text{s}$), the system fails closed into a safe `HOLD` state.

### 2. Privacy-Preserving On-Chain Audit Anchors (FISCO BCOS)
- **WeBank Consortium Chain Alignment & Banking Secrecy**:
  Instead of leaking proprietary econometric orderbook curves or client trade details in plaintext on-chain, Tec-C commits cryptographic SHA-256 commitments to FISCO BCOS:
  $$\text{RecordHash} = \text{SHA256}\Big(\text{account} \;\parallel\; \text{symbol} \;\parallel\; \text{action} \;\parallel\; P_{\text{cons}} \;\parallel\; \text{timestamp} \;\parallel\; \text{salt}\Big)$$
- Emits an `AuditRecordAnchored` event on the consortium chain, allowing instant regulatory verification (PBOC/CSRC/WeBank) while preserving complete commercial privacy at **$0.00 gas fee**.

### 3. Market Microstructure Volatility Slippage Recovery
- **Flash Panic Orderbook Thinning Defense**:
  When sudden volatility causes a DEX execution to revert with `SLIPPAGE_EXCEEDED`, Tec-C automatically cuts order size in half ($Q^*/2$).
- **Positive Expected Carry Invariant**:
  Before resubmitting, verifies that expected carry value remains strictly positive ($E[\Delta V] > 0$). Submits the halved recovery order once, preventing infinite retry loops and gas draining.

### 4. Zero Mandatory Cost Market Data Design
- **100% Operable Without Paid Subscriptions**:
  Integrates Chainlink decentralized oracles, DeFiLlama REST, Binance public tickers, and Alternative.me sentiment without requiring any paid API key.
- **Enterprise Comparative Catalog**:
  Documents $100k+/year institutional feeds (Bloomberg, Kaiko, Amberdata, CoinAPI, Nansen) and maps each to a zero-cost open alternative.

---

## 🧪 Comprehensive Test Results (100% Pass Rate)

### 1. Smart Contracts Layer: 170 / 170 Passing Tests (Foundry)
```bash
Ran 14 test suites: 170 tests passed, 0 failed, 0 skipped (170 total tests)
```
- `PrivacyAuditAnchorTest`: 3 passed (Cryptographic digest anchoring, zero-hash rejection, replay defense)
- `WebAuthnP256ValidatorTest`: 15 passed (RIP-7212 precompile `0x100`, pure-Solidity fallback, low-$s$, UV & recovery)
- `TetherGuardHookTest`: 37 passed (Velocity limits, dynamic elasticity, biometric breakout, morning review)
- `TecPaymasterTest`: 6 passed (Gas sponsorship & anti-griefing limits)
- `CrossChainTetherTest`: 7 passed (Multi-chain aggregate lock & par-repo facility)
- `DeadmanAndHeartbeatTest`: 10 passed (AI heartbeat watchdog & 90-day deadman switch)
- `VaultComprehensiveFuzzTest`: 5 passed (256 fuzz runs each)
- `VaultSecurityHardeningTest`: 18 passed (SEC-01..08 security regression invariants)
- `VaultEdgeCasesTest`: 19 passed (Zero-value & boundary conditions)
- `VaultLifecycleScenariosTest`: 4 passed (Multi-day enterprise lifecycles)
- `SessionKeyValidatorTest`: 8 passed (EIP-712 AI mandate verification)
- `VaultGasBenchmarkTest`: 19 passed (Multi-chain empirical gas matrix)
- `MultiTokenTetherTest`: 12 passed (Multi-token pricing & USD normalization)
- `TecAccountTest`: 7 passed (ERC-7579 modular account execution)

### 2. Python AI Brain & Risk Engine: 622 / 622 Passing Tests (Pytest)
```bash
622 passed, 11 warnings in 33.98s (100% passing)
```
- `test_fisco_node.py`: 8 passed (Automated cluster supervisor, health probing, WSL idle timeout management, clean shutdown)
- `test_slippage_recovery.py`: 4 passed (Slippage detection, order halving $Q^*/2$, positive carry verification, loop prevention)
- `test_audit_anchor.py`: 2 passed (Deterministic SHA-256 record hashing, on-chain anchor submission & verification)
- `test_market_live_feeds.py`: 3 passed (Live feeds catalog, free vs paid mapping, offline fallback)
- `test_virtual_session.py`: 10 passed (Cloudflare Quick-Tunnel, WebAuthn pairing, step-up tokens, route isolation)
- `test_pegguard.py`: 20 passed (5-layer arbitrage engine, 25-asset catalog, watermark memory)
- `test_biometrics.py`: 15 passed (NIST P-256 signing, low-$s$ normalization, UP/UV authenticatorData parser, guardian recovery)
- `test_pipeline.py`, `test_brain.py`, `test_planner.py`: Cognitive intent parser, firewall sieve, and risk engine

---

## 🚀 Quickstart & Verification Commands

### Smart Contracts Test Suite
```bash
cd contracts
forge test
```

### Smart Contract Bytecode Sizes (EIP-170 Compliance)
```bash
cd contracts
forge build --sizes
```

### Python Multi-Agent Test Suite
```bash
cd agent
.\.venv\Scripts\pytest
```

### Run Dual Server Virtual Session (Admin App + Mobile Gateway)
```bash
cd agent
.\.venv\Scripts\python -m tecc_brain.virtual_session.runner
```

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).

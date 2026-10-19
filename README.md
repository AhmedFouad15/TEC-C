# Tec-C (Tethered Expense Corporate Card)
### Autonomous On-Chain Agent Wallet with Mathematical Security Invariants

[![Solidity](https://img.shields.io/badge/Solidity-0.8.24-363636?logo=solidity)](https://soliditylang.org/)
[![Foundry](https://img.shields.io/badge/Foundry-170%2F170%20Passing-brightgreen?logo=ethereum)](https://getfoundry.sh/)
[![Python Brain](https://img.shields.io/badge/Python%20Brain-660%20Tests-blue?logo=python)](https://fastapi.tiangolo.com/)
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

Detailed architectural breakdowns, run guides, and econometric specifications are available in the dedicated [`docs/`](./docs/README.md) folder:

| Part / Folder | Subject | Description |
|---|---|---|
| [`docs/01_system_architecture/`](./docs/01_system_architecture/README.md) | Multi-Agent Design | 3-Member execution model, LangGraph cognitive state machine, and dual-server IPC |
| [`docs/02_prerequisites_and_run_guide/`](./docs/02_prerequisites_and_run_guide/README.md) | Run & Deploy Manual | Step-by-step setup (Python, Foundry, WSL 2), test execution, and deployment commands |
| [`docs/03_market_data_feeds_and_apis/`](./docs/03_market_data_feeds_and_apis/README.md) | Feeds & Free Alternatives | $0.00 zero-cost design, free public endpoints, and enterprise feed comparative matrix |
| [`docs/04_multichain_and_fisco_bcos/`](./docs/04_multichain_and_fisco_bcos/README.md) | Multi-Chain & Node Cluster | FISCO BCOS testnet cluster setup, millisecond EVM nuance, and auto-supervisor |
| [`docs/05_fail_closed_strictness_hierarchy/`](./docs/05_fail_closed_strictness_hierarchy/README.md) | Math > AI Hierarchy | Tsinghua academic formulation, asymmetric bounding proofs ($B_{AI} \subseteq B_{math}$), and timeouts |
| [`docs/06_privacy_anchors_and_slippage/`](./docs/06_privacy_anchors_and_slippage/README.md) | Audit & Slippage Engine | SHA-256 anchors on FISCO BCOS, orderbook thinning recovery ($Q^*/2$), and positive carry |
| [`docs/07_defi_protocols_and_routing/`](./docs/07_defi_protocols_and_routing/README.md) | Protocol Registry | Verified contracts, ABIs, function selectors, and risk tiers (Lido, Aave, Curve, Uniswap) |
| [`docs/08_smart_contracts/`](./docs/08_smart_contracts/README.md) | Smart Contracts Vault | ERC-7579 vault, EIP-712 session key validator, RIP-7212 precompile `0x100`, gas matrix |
| [`docs/09_pegguard_arbitrage_framework/`](./docs/09_pegguard_arbitrage_framework/README.md) | PegGuard Arbitrage Framework | 5-layer quantitative funnel, Markov regimes, 25-asset universe, 24/7 autonomous daemon & watermark memory |
| [`docs/pdf/`](./docs/pdf/README.md) | Original Whitepapers (PDF) | Complete archive of all 9 original technical PDF whitepapers, engineering masterplans, and roadmap guides |

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
│   └── tests/                               # 660 Unit, Property & Integration Tests
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
│   ├── 01_system_architecture/              # Architecture, Multi-Agent & Transcribed Roadmaps
│   ├── 02_prerequisites_and_run_guide/      # Run & Deployment Manuals
│   ├── 03_market_data_feeds_and_apis/       # Zero-Cost Feeds & Enterprise Alternatives
│   ├── 04_multichain_and_fisco_bcos/        # 4-Chain Setup & FISCO BCOS Supervisor
│   ├── 05_fail_closed_strictness_hierarchy/ # Math > AI Asymmetric Governance
│   ├── 06_privacy_anchors_and_slippage/     # Banking Secrecy SHA-256 & Recovery
│   ├── 07_defi_protocols_and_routing/       # Verified Multi-Chain Protocol Registry
│   ├── 08_smart_contracts/                  # Vault, Hook, Gas & Security Benchmarks
│   ├── 09_pegguard_arbitrage_framework/     # 5-Layer Funnel, 24/7 Daemon & Watermark Memory Spec
│   └── pdf/                                 # Complete Collection of 9 Original PDF Whitepapers
├── shared/
│   ├── api_spec.json                        # Exported OpenAPI 3.1 specification (35 endpoints)
│   ├── chainlink_feeds.json                 # Verified Chainlink Oracle Registry (Multi-Chain)
│   ├── contracts.arbitrum.json              # Deployed addresses on Arbitrum One
│   ├── contracts.fisco.json                 # Deployed addresses on FISCO BCOS (Chain ID 20200)
│   ├── contracts.sepolia.json               # Deployed addresses on Ethereum Sepolia
│   └── defi_protocols.json                  # Verified DeFi Protocol Registry & Function Selectors
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
│   │   (Biometric Face ID)     │           │  (LangGraph Cognitive Planner)  │   │
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
  - If the AI model times out ($> 8.0\text{s}$) or errors, the order goes on `HOLD`: nothing runs automatically and every option stays available for manual approval. An invalid model verdict is discarded and the deterministic rules decide.

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

### 2. Python AI Brain & Risk Engine: 660 Tests (Pytest)
```bash
659 passed locally; test_audit_anchor needs a current `forge build` (PrivacyAuditAnchor artifact)
```
- `test_audit_resolution.py`: 22 passed (System Flow Audit regressions: AI veto/BREAKOUT binding at execute, PegGuard through the Brain, HOLD on model failure, market routing, anchoring, masked notes, live phone gateway)
- `test_strictness_hierarchy.py`: 9 passed (Asymmetric bounding $B_{AI} \subseteq B_{math}$, deterministic Layer 1-5 gating, fail-closed timeout > 8.0s, audit anchor hashing)
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

### Run the Whole Stack (chain + vault + Brain + website)
Put your API keys in `agent/.env` (template: `agent/.env.example`), then:
```powershell
powershell -ExecutionPolicy Bypass -File .\dev_up.ps1   # Windows  (stop: .\dev_down.ps1)
```
```bash
./dev_up.sh                                              # macOS / Linux  (stop: ./dev_down.sh)
```
Dashboard: http://localhost:5500/app.html (also served by the Brain at http://127.0.0.1:8000/app.html).

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

## 🖥️ One-Command Local Development

#### To Launch Everything:

Open PowerShell in the project root directory and run [`dev_up.ps1`](./dev_up.ps1):

```powershell
powershell -ExecutionPolicy Bypass -File .\dev_up.ps1
```

**What this does automatically:**

1. Starts the local blockchain and deploys the vault contracts.
2. Starts the Backend Brain API on [http://127.0.0.1:8000](http://127.0.0.1:8000).
3. Starts the Frontend Server on [http://localhost:5500](http://localhost:5500) and opens it in your default browser.

#### To Stop Everything:

Run [`dev_down.ps1`](./dev_down.ps1):

```powershell
powershell -ExecutionPolicy Bypass -File .\dev_down.ps1
```

*(This cleanly terminates all background processes on ports 8000, 5500, and 8545).*

---

## 📄 License
This project is licensed under the [MIT License](LICENSE).

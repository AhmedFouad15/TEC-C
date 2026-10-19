# Tec-C: Complete System Documentation Directory

Welcome to the technical documentation for **Tec-C (Tethered Expense Corporate Card)** — an autonomous, multi-chain agent wallet built with mathematical risk invariants, cryptographic policy enforcement, and consortium banking compliance.

---

## 📂 Documentation Structure by Domain

Each core component has a dedicated folder containing comprehensive technical explanations, formal invariants, and operational guides:

| Folder | Domain | Core Content |
|---|---|---|
| [`01_system_architecture/`](./01_system_architecture/README.md) | **System Architecture** | Multi-Agent cognitive graph, 3-Member execution model, LangGraph state machine, dual-server runner. |
| [`02_prerequisites_and_run_guide/`](./02_prerequisites_and_run_guide/README.md) | **Prerequisites & Run Guide** | System requirements (Python 3.10+, Foundry, WSL 2), step-by-step setup, test execution, and deployment manual. |
| [`03_market_data_feeds_and_apis/`](./03_market_data_feeds_and_apis/README.md) | **Market Data Feeds & APIs** | Zero-cost design ($0.00 / no paid keys required), Chainlink oracles, and enterprise alternatives comparative catalog. |
| [`04_multichain_and_fisco_bcos/`](./04_multichain_and_fisco_bcos/README.md) | **Multichain & FISCO BCOS** | 4-chain topology (Ethereum, Base, Arbitrum, FISCO BCOS), official v3.17.1 node supervisor, and EVM RPC normalization. |
| [`05_fail_closed_strictness_hierarchy/`](./05_fail_closed_strictness_hierarchy/README.md) | **Math > AI Strictness Hierarchy** | Tsinghua PBCSF academic panel framing, mathematical asymmetric bounding ($B_{AI} \subseteq B_{math}$), and fail-closed timeout logic. |
| [`06_privacy_anchors_and_slippage/`](./06_privacy_anchors_and_slippage/README.md) | **Privacy Anchors & Resilience** | WeBank banking secrecy, SHA-256 on-chain audit anchors, and flash-panic order halving ($Q^*/2$) recovery. |
| [`07_defi_protocols_and_routing/`](./07_defi_protocols_and_routing/README.md) | **DeFi Protocols & Routing** | Verified multi-chain DeFi protocol registry (Lido, Aave v3, Curve, Uniswap v3, Compound v3, Shibor MMF, PAXG). |
| [`08_smart_contracts/`](./08_smart_contracts/README.md) | **Smart Contracts Architecture** | ERC-7579 vault, EIP-712 session key validator, RIP-7212 precompile `0x100`, gas benchmarks, and EIP-170 compliance. |
| [`09_pegguard_arbitrage_framework/`](./09_pegguard_arbitrage_framework/README.md) | **PegGuard Arbitrage Framework** | 5-layer quantitative funnel, Markov regime switching, 25-asset universe, 24/7 background daemon, and stateful watermark memory. |
| [`pdf/`](./pdf/README.md) | **Original Technical Whitepapers (PDF)** | Complete collection of all 9 original technical PDF whitepapers, engineering roadmaps, and specification documents. |

---

## 🗂️ Detailed File Catalog per Folder

```
docs/
├── 01_system_architecture/
│   ├── README.md                                                 # Architecture Overview & Multi-Agent Flow
│   ├── BRAIN_DESIGN.md                                           # Cognitive AI & Strategy Engine Spec
│   ├── INTAKE_AND_ORCHESTRATOR.md                                # Intake Layer (/draft -> /confirm) & Orchestration
│   ├── PROJECT_SPECIFICATION.md                                  # Transcribed from project.pdf (Master Specification)
│   ├── EXECUTION_ROADMAP.md                                      # Transcribed from excution.pdf (Sequential Masterplan)
│   ├── PLAIN_ENGLISH_GUIDE.md                                    # Transcribed from Tec-c_Plain_English_Guide.pdf
│   └── FOUR_PERSON_ROADMAP.md                                    # Transcribed from Tec-C_4_Person_Execution_Roadmap.pdf
├── 02_prerequisites_and_run_guide/
│   ├── README.md                                                 # Prerequisites, Foundry & Pytest Setup Manual
│   ├── DEPLOYMENT_AND_RUN.md                                     # Production Dual-Server & Live Testing Guide
│   ├── HOW_IT_WORKS_GUIDE.md                                     # Transcribed from Tec-C_How_It_Works_Guide.pdf
│   └── VIRTUAL_SESSION_DESIGN.md                                 # Transcribed from Virtual_Session_Design.pdf
├── 03_market_data_feeds_and_apis/
│   ├── README.md                                                 # Zero-Cost Market Feeds & Free Alternative Mapping
│   └── ORACLE_AND_PRICING_CATALOG.md                             # Chainlink Oracles, Endpoints & Price Feeds Spec
├── 04_multichain_and_fisco_bcos/
│   ├── README.md                                                 # 4-Chain Setup & Official FISCO BCOS Node Guide
│   ├── MULTICHAIN_NODES.md                                       # Making Simulated Markets Real (Step-by-Step)
│   └── MAKING_MARKETS_REAL.md                                    # Transcribed from TecC_Making_Markets_Real.pdf
├── 05_fail_closed_strictness_hierarchy/
│   ├── README.md                                                 # Tsinghua PBCSF Formulation & Math Governance
│   └── FORMAL_ASYMMETRIC_BOUNDS.md                              # Mathematical Invariant Proofs (B_AI ⊆ B_math)
├── 06_privacy_anchors_and_slippage/
│   ├── README.md                                                 # WeBank Consortium Secrecy & Slippage Recovery
│   └── AUDIT_ANCHOR_SPECIFICATION.md                             # SHA-256 On-Chain Commitment & Event Spec
├── 07_defi_protocols_and_routing/
│   ├── README.md                                                 # Verified Multi-Chain DeFi Protocol Registry
│   └── VENUE_ROUTING_MATRIX.md                                   # Smart Contract ABIs, Selectors & Whitelist
├── 08_smart_contracts/
│   ├── README.md                                                 # ERC-7579 Vault, EIP-712 Session Key & Hook Spec
│   ├── SECURITY_AND_GAS_BENCHMARKS.md                            # Gas Benchmarks & EIP-170 Compliance Analysis
│   └── VAULT_ARCHITECTURE_GUIDE.md                               # Transcribed from Tec-C_Vault_User_and_Architecture_Guide.pdf
├── 09_pegguard_arbitrage_framework/
│   ├── README.md                                                 # 5-Layer Funnel, 24/7 Daemon & Watermark Memory Spec
│   └── PEGGUARD_SPECIFICATION.md                                 # Transcribed from PegGuard.pdf (12-Page Master Whitepaper)
└── pdf/
    ├── README.md                                                 # Index of All Original Technical PDFs & Whitepapers
    ├── PegGuard.pdf                                              # Master Quantitative Peg Arbitrage Whitepaper
    ├── excution.pdf                                              # Master Technical Roadmap
    ├── project.pdf                                               # Core Project Specification
    ├── Tec-C_4_Person_Execution_Roadmap.pdf                      # Engineering Workstream Map
    ├── Tec-C_How_It_Works_Guide.pdf                              # System & UI Operational Guide
    ├── Tec-c_Plain_English_Guide.pdf                             # Plain English Architecture Moats
    ├── Tec-C_Vault_User_and_Architecture_Guide.pdf               # Vault System & Invariants Manual
    ├── TecC_Making_Markets_Real.pdf                              # FISCO BCOS & Multi-Market Nodes Manual
    └── Virtual_Session_Design.pdf                                # Dual-Server & Biometric Session Design
```

---

## 🧭 Navigation Guide for Reviewers & Judges

### For Academic Judges (Tsinghua University PBCSF):
* Start with [`05_fail_closed_strictness_hierarchy/`](./05_fail_closed_strictness_hierarchy/README.md) to review how mathematical models (Markov-switching AR(1), CVaR bounds, Sharpe filters) strictly govern probabilistic LLM outputs.
* Review [`09_pegguard_arbitrage_framework/`](./09_pegguard_arbitrage_framework/README.md) for the 5-layer econometric funnel, Jump-Diffusion duration SDE, and Death-Spiral Canary ($\beta \ge 1.0$).
* Review [`01_system_architecture/`](./01_system_architecture/README.md) for the 3-member multi-agent cognitive architecture.

### For Enterprise & Consortium Evaluators (WeBank):
* Start with [`06_privacy_anchors_and_slippage/`](./06_privacy_anchors_and_slippage/README.md) to inspect how proprietary orderbook alpha is kept private off-chain while committing SHA-256 regulatory hashes to FISCO BCOS.
* Review [`04_multichain_and_fisco_bcos/`](./04_multichain_and_fisco_bcos/README.md) for official FISCO BCOS node integration and EVM millisecond compatibility.

### For Developers & Quant Engineers:
* Start with [`02_prerequisites_and_run_guide/`](./02_prerequisites_and_run_guide/README.md) to run the 170 Foundry tests and 637 Pytest suites locally.
* Review [`09_pegguard_arbitrage_framework/`](./09_pegguard_arbitrage_framework/README.md) for the 25-asset peg arbitrage scanner, live feed integration, and watermark memory.
* Review [`03_market_data_feeds_and_apis/`](./03_market_data_feeds_and_apis/README.md) and [`07_defi_protocols_and_routing/`](./07_defi_protocols_and_routing/README.md) for market integrations and smart contract addresses.
* Inspect [`pdf/`](./pdf/README.md) for original reference PDFs and architectural whitepapers.

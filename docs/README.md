# Tec-C: Complete System Documentation Directory

Welcome to the technical documentation for **Tec-C (Tethered Expense Corporate Card)** — an autonomous, multi-chain agent wallet built with mathematical risk invariants, cryptographic policy enforcement, and consortium banking compliance.

---

## 📂 Documentation Structure by Domain

Each core component has a dedicated folder containing comprehensive technical explanations, formal invariants, and operational guides:

| Folder | Domain | Core Content |
|---|---|---|
| [`01_system_architecture/`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/01_system_architecture/README.md) | **System Architecture** | Multi-Agent cognitive graph, 3-Member execution model, LangGraph state machine, dual-server runner. |
| [`02_prerequisites_and_run_guide/`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/02_prerequisites_and_run_guide/README.md) | **Prerequisites & Run Guide** | System requirements (Python 3.10+, Foundry, WSL 2), step-by-step setup, test execution, and deployment manual. |
| [`03_market_data_feeds_and_apis/`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/03_market_data_feeds_and_apis/README.md) | **Market Data Feeds & APIs** | Zero-cost design ($0.00 / no paid keys required), Chainlink oracles, and enterprise alternatives comparative catalog. |
| [`04_multichain_and_fisco_bcos/`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/04_multichain_and_fisco_bcos/README.md) | **Multichain & FISCO BCOS** | 4-chain topology (Ethereum, Base, Arbitrum, FISCO BCOS), official v3.17.1 node supervisor, and EVM RPC normalization. |
| [`05_fail_closed_strictness_hierarchy/`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/05_fail_closed_strictness_hierarchy/README.md) | **Math > AI Strictness Hierarchy** | Tsinghua PBCSF academic panel framing, mathematical asymmetric bounding ($B_{AI} \subseteq B_{math}$), and fail-closed timeout logic. |
| [`06_privacy_anchors_and_slippage/`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/06_privacy_anchors_and_slippage/README.md) | **Privacy Anchors & Resilience** | WeBank banking secrecy, SHA-256 on-chain audit anchors, and flash-panic order halving ($Q^*/2$) recovery. |
| [`07_defi_protocols_and_routing/`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/07_defi_protocols_and_routing/README.md) | **DeFi Protocols & Routing** | Verified multi-chain DeFi protocol registry (Lido, Aave v3, Curve, Uniswap v3, Compound v3, Shibor MMF, PAXG). |

---

## 🧭 Navigation Guide for Reviewers & Judges

### For Academic Judges (Tsinghua University PBCSF):
* Start with [`05_fail_closed_strictness_hierarchy/`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/05_fail_closed_strictness_hierarchy/README.md) to review how mathematical models (Markov-switching AR(1), CVaR bounds, Sharpe filters) strictly govern probabilistic LLM outputs.
* Review [`01_system_architecture/`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/01_system_architecture/README.md) for the 3-member multi-agent cognitive architecture.

### For Enterprise & Consortium Evaluators (WeBank):
* Start with [`06_privacy_anchors_and_slippage/`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/06_privacy_anchors_and_slippage/README.md) to inspect how proprietary orderbook alpha is kept private off-chain while committing SHA-256 regulatory hashes to FISCO BCOS.
* Review [`04_multichain_and_fisco_bcos/`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/04_multichain_and_fisco_bcos/README.md) for official FISCO BCOS node integration and EVM millisecond compatibility.

### For Developers & Quant Engineers:
* Start with [`02_prerequisites_and_run_guide/`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/02_prerequisites_and_run_guide/README.md) to run the 170 Foundry tests and 637 Pytest suites locally.
* Review [`03_market_data_feeds_and_apis/`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/03_market_data_feeds_and_apis/README.md) and [`07_defi_protocols_and_routing/`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/docs/07_defi_protocols_and_routing/README.md) for market integrations and smart contract addresses.

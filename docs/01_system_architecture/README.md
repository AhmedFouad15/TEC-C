# Tec-C: System Architecture & Multi-Agent Design

> **Project**: Tec-C (Tethered Expense Corporate Card)  
> **Topic**: Topic F: Agent Wallet  
> **Hosts**: Tsinghua University PBCSF & WeBank  
> **Track**: Shenzhen International FinTech Competition (FinTechathon 2026)

---

## 1. High-Level Vision & Architecture

Tec-C is an institutional-grade Autonomous Agent Wallet designed for multi-market execution across DeFi, commodities, and consortium markets. It enables autonomous AI agents to execute daily treasury and risk-adjusted yield operations under mathematically unbreakable cryptographic, econometric, and smart-contract bounds.

The system is partitioned into three collaborating members:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Member 3: Mobile & Passkey Interface                 │
│  - Flutter Cross-Platform Wallet UI                                    │
│  - Hardware-Bound WebAuthn Passkeys (W3C / FIDO2 secp256r1)           │
│  - Biometric FaceID Morning Review & Emergency Recovery                │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ EIP-712 Session Mandate
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  Member 2: Cognitive Brain & Orchestrator              │
│  - Gatekeeper Intake & Prompt-Injection Firewall                       │
│  - Econometric & Liquidity Engine (Sharpe, CVaR95, Contagion)          │
│  - PegGuard 5-Layer Regime-Switching Arbitrage Engine                  │
│  - Multi-Market Router (Ethereum, Arbitrum, FISCO BCOS)                │
│  - Privacy-Preserving On-Chain Audit Anchoring                         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ ERC-4337 UserOps / Signed Sessions
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  Member 1: Modular Smart Accounts (EIP-7579)           │
│  - TecAccount: Modular Smart Account Execution Core                    │
│  - TetherGuardHook: Tether Radius, Elasticity, Whitelist & Deadman     │
│  - SessionKeyValidator: 117-byte ECDSA / ERC-1271 Mandate Verification │
│  - TecPaymaster: Enterprise Zero-Gas Sponsorship Quotas                │
│  - PrivacyAuditAnchor: Cryptographic Audit Trail on FISCO BCOS         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Multi-Agent Cognitive Pipeline (Member 2)

The Brain is implemented as a deterministic LangGraph state machine with seven specialized agents:

1. **Gatekeeper Intake (`gatekeeper_intake`)**:
   - Sanitizes untrusted user text using regex heuristics and zero-shot classifiers.
   - Masks sensitive financial identifiers (IBANs, card numbers, private keys) before any downstream processing.
2. **Profile Agent (`profile`)**:
   - Maintains a local, learned Bayesian model of user risk tolerance ($\lambda$ loss aversion, $\tau$ trust factor).
   - Loads historical approvals and explicit user preference constraints.
3. **NLP Risk Sentinel (`nlp_sentinel`)**:
   - Pulls live market snapshots (Chainlink, DeFiLlama, Binance, Fear & Greed).
   - Categorizes asset distress across 3 Markov regimes (`normal`, `temporary distress`, `failure`).
4. **Econometric & Liquidity Agent (`econometric_liquidity`)**:
   - Applies hard exclusion filters (regulatory sanctions, asset whitelist, risk tier caps).
   - Calculates forward-looking risk-adjusted scores (Sharpe ratio, 95% CVaR tail risk).
5. **Gatekeeper Aggregator (`gatekeeper_aggregator`)**:
   - Generates the deterministic rule-based options baseline (`Good`, `Better`, `Best`).
6. **AI Brain Synthesis (`brain`)**:
   - Single-pass LLM assessment that operates under the strict invariant: **Math > AI**.
   - The AI can only tighten bounds, lower sizes, or veto candidates—it can never expand autonomy or override quantitative rejections.
7. **Web3 Executor (`web3_executor`)**:
   - Converts the approved execution intent into a signed on-chain session transaction.

---

## 3. Dual-Server Virtual Session Architecture

To bridge institutional web environments with mobile devices securely:

```
[Flutter Mobile Device]
       │
       ▼ (HTTPS over Internet)
[Cloudflare Quick Tunnel] (*.trycloudflare.com)
       │
       ▼ (Forwarded to Localhost)
[Mobile Gateway: 127.0.0.1:8001] (Session creation, EIP-712 mandate signing, WebAuthn)
       │
       ▼ (Internal IPC)
[Admin Brain Server: 127.0.0.1:8000] (NEVER exposed to Internet; LLM synthesis, Web3 keys)
```

- **Admin Server (`127.0.0.1:8000`)**: Contains private session signing keys and core execution logic. Strictly bound to loopback; never exposed through tunnels.
- **Mobile Gateway (`127.0.0.1:8001`)**: Lightweight session ingestion proxy exposed via a free Cloudflare Quick Tunnel for live mobile device pairing.

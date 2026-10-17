# Deferred Issues

## Open

### ISS-001: Regex firewall cannot be complete
- **Discovered:** Phase 4, plan 04-02 (three background security reviews of firewall.py)
- **Type:** Security hardening (enhancement)
- **Description:** Pattern matching is hardened (NFKC, invisible chars, confusables, small caps, mixed scripts,
  squashed/leetspeak pass, encoded blobs, DID smuggling) but no regex filter catches every paraphrase a language model
  understands (e.g. "move the whole stash to my other place").
- **Why it is acceptable now:** the guarantees are structural, not textual — the Brain has no transfer action,
  Mandate.recipients is always empty, the planner only allocates to whitelisted venues, and TetherGuardHook reverts
  unauthorised targets on-chain.
- **Possible fix:** once an LLM provider is chosen, add a second classifier pass on the approved text (fail closed),
  and red-team the firewall with a generated attack corpus.
- **Effort:** Medium

### ISS-002: Sieve does not mask personal names
- **Discovered:** Phase 4, background security review of sieve.py (privacy leak, fixed for numbers/addresses)
- **Type:** Privacy hardening (enhancement)
- **Description:** Numbers, EVM/base58/bech32 addresses, tx hashes, DIDs, ENS and emails are masked (fail closed).
  Chinese numerals and English number words are masked too (fixed after a second review). Names ("my CFO Wang Lei")
  and obfuscated emails ("alice [at] example [dot] com") are not.
- **Why acceptable now:** no LLM provider is configured, so nothing leaves the machine; demo requests carry no names.
- **Possible fix:** local NER pass (spaCy, already in Member 4's stack) before any cloud call.
- **Effort:** Small–Medium

### ISS-003: Multi-Chain Deployment & Upgraded News Risk Sentinel Review (For Khaled / Member 2)
- **Discovered:** Multi-chain vault and upgraded news layer integration
- **Type:** Architecture & Code Review
- **Assignee:** Khaled (@member2)
- **Status:** Ready for Review (Branches: `main` & `member2/brain`)
- **Key Deliverables to Review:**
  1. **Multi-Chain Solidity Deployments (`contracts/script/DeployMultiChainTecC.s.sol`):**
     - Ethereum/Sepolia (Crypto Market): Lido staking, Curve stETH/ETH LP, Aave/Compound lending.
     - Arbitrum One (Commodities Market - Chain ID 42161): PAXG physical gold (`paxg_hold`) with Nitro sequencer gas discounts.
     - FISCO BCOS (Consortium Market - Chain ID 2026): Onshore Shibor MMF (`shibor_mmf`) with native enterprise zero-gas sponsorship ($0.00 gas fee for cardholders).
  2. **Multi-Chain Shared Configurations & Network Loaders:**
     - `shared/contracts.arbitrum.json` and `shared/contracts.fisco.json`.
     - `agent/tecc_brain/onchain/network.py`: network selection supporting `"anvil"`, `"sepolia"`, `"arbitrum"`, `"fisco_bcos"` via `load_arbitrum_deployment()` and `load_fisco_deployment()`.
  3. **Multi-Market Executors & PegGuard Stub (`agent/tecc_brain/onchain/executor.py`):**
     - `CryptoExecutor`: Dispatches by exchange venue and `ActionType` (`STAKE`, `SWAP`/`BUY_DISCOUNT`, `DEPOSIT`/`OPTIMIZE_YIELD`, `TRANSFER`).
     - `FiscoBcosExecutor`: Consortium rail with $0.00 zero-fee receipts.
     - `ArbitrumCommoditiesExecutor`: Nitro L2 commodity bridge execution.
     - `PegGuardArbitrageExecutor`: Blank stub pending completion of the PegGuard module.
     - `MarketRouter`: Unified router dispatching on `ExecutionIntent.market`.
  4. **Upgraded News Risk Layer (`agent/tecc_brain/sentinel/`):**
     - **Principle:** Retail Emotions (Contrarian) vs Fundamentals & Smart-Money (Directional Veto).
     - **Pipeline 1 (Market Statement Score $M \in [0, 1]$):**
       $$M = 0.35 \cdot \text{CMC} + 0.35 \cdot \text{Grok Macro} + 0.30 \cdot \text{CoinGlass Macro}$$
       * CMC Fear & Greed: Sigmoid tail amplification + reversal velocity boost ($\Delta FG$).
       * Grok X-Pulse: Structured JSON rubric (`retail_capitulation_index` vs `retail_euphoria_index`).
       * CoinGlass Macro: Global 24h long liquidation flush ($>75\%$) + negative funding.
     - **Pipeline 2 (Token Check Score $S_{Token} \in [0, 1]$):**
       $$S_{Token} = \mathbb{I}_{Safe} \times \left(0.45 \cdot C_{CoinGlass} + 0.30 \cdot F_{FinBERT} + 0.25 \cdot G_{Grok}\right)$$
       * **GATE 0 Circuit Breaker ($\mathbb{I}_{Safe} \in \{0, 1\}$):** If structural insolvency trigger (`exploit`, `drained`, `de-peg`, `bankruptcy`, `redemptions halted`, `wells notice`) detected with $P(\text{negative}) > 0.85$, forces $\mathbb{I}_{Safe} = 0 \implies S_{Token} = 0.0$ (Hard Veto / Immediate Sell).
       * **Pillar A (CoinGlass 45%):** OI vs Price divergence, funding rate squeeze, whale vs retail L/S ratio, spot vs perp CVD divergence.
       * **Pillar B (FinBERT 30%):** Exponential time-decay $w_i = e^{-\lambda \Delta t_i}$ ($\lambda = 0.03$).
       * **Pillar C (Grok 25%):** Dual-persona retail contrarian + security tracker.
- **Verification Status:**
  - 156 / 156 Foundry tests passing.
  - 442 / 442 Python tests passing.
  - Zero occurrences of prohibited words.
- **Effort:** Review & Feedback


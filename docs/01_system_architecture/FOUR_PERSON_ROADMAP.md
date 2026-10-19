# Tec C 4 Person Execution Roadmap
> **Source PDF Document**: [`Tec-C_4_Person_Execution_Roadmap.pdf`](../09_reference_whitepapers/Tec-C_4_Person_Execution_Roadmap.pdf)  
> **Pages**: 4  
> **Transcribed & Documented for**: Tec-C Technical Documentation Suite

---

<!-- Page 1 -->

Tec-C: 4-Person Engineering Roadmap
Decoupled Full-Stack Engineering Architecture & Daily Workstreams (Oct 16 - Oct 20)
Target Event: Shenzhen FinTechathon 2026 (International Track)
Topic Track: Topic F: Agent Wallet (Autonomous On-Chain Wallet)
Co-Hosts: Tsinghua University PBCSF & WeBank
Submission Deadline: October 20, 2026 (23:59 Beijing Time)
Team Structure: 100% Technical Engineering Roster (4 Leads)
Team Compliance: ≥ 60% non-Chinese members verified
1. Executive Sprint Strategy: Dual-Lead AI Architecture
To achieve maximum technical depth for the judging panel (Tsinghua PBCSF and WeBank AI), the AI layer is decoupled across two
dedicated engineers rather than relying on a non-technical pitch lead. Member 1 builds the on-chain smart contract vault, Member 2 builds the
cognitive planning and strategy engine, Member 3 builds the user dashboard and live attack sandbox, and Member 4 builds the PegGuard
Layer 4 NLP sentinel and omni-market macro oracles. Pitch deck production, demo video recording, and final lodgement are shared across the
team.
2. The 4-Person Technical Ownership Matrix
Role & Title
Primary Technical Domain
Core Deliverable Outputs
Target Judges Satisfied
Member 1:
Smart Contracts Lead
The Vault Architect
Solidity 0.8.24, Foundry,
ERC-7579 Minimal Account,
OpenZeppelin, Anvil fork.
 TecAccount.sol (modular vault)
 TetherGuardHook.sol (immutable)
 SessionKeyValidator.sol
 TecPaymaster.sol (anti-griefing)
 100% Foundry Unit Tests
Henry Ma & Kaixiang Zhang
(WeBank Account Abstraction
& Security Standards)
Member 2:
Cognitive AI & Strategy
Lead
The Brain & Planner
Python 3.11, FastAPI,
LangGraph, Pydantic v2,
Web3.py, Local Privacy Sieve.
 LangGraph Intent Parser
 Dual-Axis Risk Profiler
 Proactive Strategy Engine ('Good, Better, Best')
 Structured UserOp Compiler
 EIP-712 WeIdentity Signer
Prof. Dacheng Xiu & Henry
Ma
(Proactive Agency, Task
Completion & Wealth UX)
Member 3:
Frontend & UX Lead
The Radar Architect
Next.js 14 (App Router), Tailwind
CSS, Lucide Icons, Wagmi, Viem,
WebAuthn Passkeys.
 Passkey Biometric Login (FaceID)
 The Tether Radius Progress Gauge
 Proactive Strategy Comparison Cards
 Breaking the Tether Modal
 The Live Attack Sandbox
Evaluation Rubric (30% UX)
(Zero seed-phrase consumer
banking experience)
Member 4:
Financial NLP & Oracles
Lead
The Sentinel & Macro Lead
Hugging Face Transformers,
ProsusAI/finbert, spaCy/NER,
Shibor/Macro APIs, Anvil fork.
 PegGuard Layer 4 NLP Sentinel
 FinBERT Adverse News Veto (≥60%)
 Omni-Market Oracle (Shibor + Gold)
 Pre-Flight Dry-Run Simulator
 Shared Pitch & Video Co-Lead
Prof. Qiang Yang, Dr. Lixin
Fan, & Prof. Jianhua Zhang
(Trustworthy AI & PBOC
Macro Standards)
Page 1 of 4
TEC-C 4-PERSON ROADMAP | SHENZHEN FINTECHATHON 2026 | TSINGHUA PBCSF & WEBANK


---

<!-- Page 2 -->

3. Member 1 Workstream: Smart Contracts & On-Chain Security
Member 1 builds the on-chain vault that guarantees user funds cannot be drained even if the AI backend is compromised:
Day & Timeline
Engineering Tasks & Implementation Scope
Verification Gate & Deliverable
Day 1 (Oct 16)
Contracts Setup
Initialize Foundry workspace. Implement TecAccount.sol (ERC-7579 minimal
account). Implement TetherGuardHook.sol enforcing The Tether Radius
($500/day default limit) and asset tier whitelist at EVM bytecode level.
Compiles cleanly with forge build. Zero
compilation warnings.
Day 2 (Oct 17)
Validator & Paymaster
Implement SessionKeyValidator.sol verifying compact 32-byte EIP-712 credential
commitments. Implement TecPaymaster.sol with 0.005 ETH session gas quota.
Launch local Anvil testnet fork with live liquidity.
Contracts deployed to local Anvil
testnet; addresses logged.
Day 3 (Oct 18)
Invariant Testing
Write comprehensive Foundry unit/fuzz tests verifying: (1) Legitimate swap
executes under limit; (2) Breaching Tether Radius reverts with
TetherRadiusExceeded(); (3) Unauthorized address reverts with
UnauthorizedTarget(); (4) Gas griefing halts at 0.005 ETH.
100% Green Tests: forge test -v
passing all tests. Export ABIs to
/shared/contracts.json.
Day 4 (Oct 19)
Gas Profiling
Run automated gas profiling reports (forge test --gas-report) proving ~3,800 gas
verification. Provide transaction hashes and contract addresses to team for video
recording.
Gas benchmark report generated;
contract addresses shared.
Day 5 (Oct 20)
Code Freeze
Add comprehensive NatSpec docstrings; clean commit history; tag stable release
on GitHub repository.
Smart contract layer frozen and public
on GitHub.
4. Member 2 Workstream: Cognitive AI & Proactive Strategy Engine
Member 2 builds the intent state machine, local privacy sieve, and the proactive multi-option strategy generator:
Day & Timeline
Engineering Tasks & Implementation Scope
Verification Gate & Deliverable
Day 1 (Oct 16)
FastAPI Scaffolding
Scaffold /agent repository with Python 3.11, FastAPI, and LangGraph. Implement
natural-language intent parser translating commands (*'Stake my 10 ETH'*) into
typed Pydantic models. Implement local PII masking (redacting balances and user
identity).
POST /api/mandate/parse returns
structured Pydantic JSON.
Day 2 (Oct 17)
Dual-Axis Risk Engine
Build the Dual-Axis Risk Profiler calibrating Axis 1 (Asset Universe: Conservative
vs Balanced vs Aggressive) and Axis 2 (The Tether Radius: $250 vs $1,000 vs
$2,500). Integrate mandate validator ensuring operations respect asset tiers.
Risk parameters successfully configure
session key scopes.
Day 3 (Oct 18)
Proactive Strategy
Build the 'Good, Better, Best' recommendation engine (evaluating Lido staking @
3.1% vs Curve stETH/ETH LP @ 6.85%). Build UserOp encoder signing EIP-712
WeIdentity credential digests. Connect to Member 1's Anvil testbed.
UserOp formatted with valid EIP-712
credential signatures.
Day 4 (Oct 19)
Backend Integration
Finalize core endpoints for Member 3's UI: /api/mandate/parse,
/api/mandate/propose, and /api/mandate/execute. Connect with Member 4's NLP
risk veto feed.
End-to-end intent to execution flow
operational.
Day 5 (Oct 20)
Docs & Freeze
Package Python dependencies in requirements.txt; generate Swagger OpenAPI
documentation (/docs).
Backend API fully documented and
reproducible.
Tec-C | 4-Person Engineering Roadmap & Technical Workstreams (Topic F)
Page 2 of 4
TEC-C 4-PERSON ROADMAP | SHENZHEN FINTECHATHON 2026 | TSINGHUA PBCSF & WEBANK


---

<!-- Page 3 -->

5. Member 3 Workstream: Frontend UI, Biometrics & Attack Sandbox
Member 3 delivers the visual dashboard, Passkey WebAuthn login, and the interactive Attack Sandbox for judges:
Day & Timeline
Engineering Tasks & Implementation Scope
Verification Gate & Deliverable
Day 1 (Oct 16)
Next.js 14 Setup
Scaffold /frontend using Next.js 14 (App Router), Tailwind CSS, Lucide Icons, and
Wagmi/Viem. Set up mock state store so UI development proceeds immediately
without waiting for backend.
App runs at localhost:3000 with dark
slate / emerald theme.
Day 2 (Oct 17)
Biometrics & Dashboard
Implement Passkey WebAuthn Login (1-tap FaceID/TouchID setup; zero seed
phrases). Build Dual-Axis Risk Selector, The Tether Radius Gauge ($ spent vs.
daily limit), and the 'Breaking the Tether' FaceID Modal.
FaceID biometric prompt triggers and
signs payload in browser.
Day 3 (Oct 18)
Attack Sandbox & Radar
Build The Live Attack Sandbox (/security) with preset judge exploit buttons
(*'Prompt Injection Drain'*, *'High-Slippage Sandwich'*), showing real-time
on-chain revert badges from TetherGuardHook. Connect Member 4's PegGuard
live news ticker.
Attack Sandbox simulates prompt
exploit and displays red revert badge.
Day 4 (Oct 19)
Integration & Polish
Connect frontend to Member 2's FastAPI endpoints and Member 1's Anvil smart
contracts. Rehearse user flow with team for 3-minute video recording.
Butter-smooth live walkthrough ready
for screen capture.
Day 5 (Oct 20)
Production Build
Run production build (npm run build); ensure 0 TypeScript or lint errors. Verify
responsiveness across screen sizes.
Production build passing with zero
errors.
6. Member 4 Workstream: Financial NLP, Omni-Market Oracles & Simulator
Member 4 builds the PegGuard Layer 4 NLP sentinel, omni-market data feeds, and pre-flight simulation engine:
Day & Timeline
Engineering Tasks & Implementation Scope
Verification Gate & Deliverable
Day 1 (Oct 16)
Omni-Market Feeds
Build data ingestion pipeline fetching live yields across Web3 DeFi (Lido 3.1%,
Aave 4.2%, Curve 6.85%), Chinese Shibor benchmarks (1M/3M/1Y rates @
2.15%), and Tokenized Gold (PAXG carry @ 1.8%).
GET /api/market/feeds returns
normalized multi-market rates.
Day 2 (Oct 17)
PegGuard NLP Pipeline
Integrate ProsusAI/finbert with Hugging Face Transformers. Build financial news
monitor (Bloomberg, Caixin, Reuters, PBOC filings). Implement Named Entity
Recognition (NER) matching protocol and issuer entities.
FinBERT accurately scores headlines;
filters entity mentions.
Day 3 (Oct 18)
Adverse Risk Veto
Implement the Asymmetric Risk Veto formula: Circuit Breaker = VETO if
P(Negative News) ≥ 60% and Entity Matched. Connect veto trigger to shrink
Tether Radius to $0 during breaking exploits.
Simulated bad news successfully
triggers emergency trade veto.
Day 4 (Oct 19)
Simulator & Demo
Assets
Build Anvil / Tenderly pre-flight dry-run simulator enforcing slippage ≤ 0.5%.
Co-lead demo video recording: capture NLP sentinel veto and cross-market yield
comparisons.
Pre-flight simulator integrated; video
assets recorded.
Day 5 (Oct 20)
Documentation & Final
Document FinBERT model weights and NLP methodology in repo; assist team
with final pitch deck diagrams and submission email lodgement.
NLP pipeline documented; final
submission verified.
Tec-C | 4-Person Engineering Roadmap & Technical Workstreams (Topic F)
Page 3 of 4
TEC-C 4-PERSON ROADMAP | SHENZHEN FINTECHATHON 2026 | TSINGHUA PBCSF & WEBANK


---

<!-- Page 4 -->

7. Zero-Blocker Interface Handoff Protocols
To guarantee that no teammate is ever blocked waiting for code from another member, follow these three explicit handoff interfaces:
Interface Handoff
Between Roles
Interface Format & Location
Zero-Blocker Fallback Protocol
Contract ABIs &
Addresses
Member 1 →
Members 2, 3, 4
/shared/contracts.json (Anvil contract addresses,
compiled JSON ABIs, and EIP-712 domain data).
Members 2, 3, 4 use predefined mock
contract ABIs until Member 1 compiles.
Backend REST & NLP APIs
Members 2 & 4 →
Member 3
/shared/api_spec.json (FastAPI Swagger OpenAPI
schema at /docs for planning & news).
Member 3 uses typed mock JSON
objects in Next.js until backend runs.
Live Demo Environment
Member 3 →
Whole Team
Running UI at http://localhost:3000 with
pre-cached demo wallets & attack presets.
Preloaded demo data allows team to
record 3-minute video cleanly in 1-2
takes.
8. Daily 18:00 Team Synchronization Milestones
Date & Day
Member 1 (Contracts)
Member 2 (Cognitive AI)
Member 3 (Frontend)
Member 4 (NLP & Oracles)
Oct 16 (Fri)
TecAccount & Hook written
Mandate parser running
Next.js shell & mocks live
Shibor & DeFi oracles live
Oct 17 (Sat)
Paymaster & Validator written
Dual-Axis risk engine ready
Passkey & Tether Gauge ready
FinBERT news pipeline live
Oct 18 (Sun)
100% Foundry tests green
Proactive strategy engine
ready
Attack Sandbox & Radar ready
NLP veto & Anvil dry-run passed
Oct 19 (Mon)
Gas report & tx hashes
logged
UserOps submitted to testbed
UI connected to API & testnet
Team records 3-minute video
Oct 20 (Tue)
Code NatSpec verified
Requirements.txt frozen
Production build passed
Team Submits to Tsinghua
9. Shared Deliverables & Final Lodgement (Due Oct 20 by 18:00 Beijing Time)
Shared Team Ownership: Pitch deck production, demo video recording, and email submission are shared across the team.
 Member 1: Provides contract transaction logs & gas benchmarks.
 Member 2: Provides intent parser traces & proactive strategy comparisons.
 Member 3: Operates the live running UI at localhost:3000 during video capture.
 Member 4: Provides FinBERT sentiment plots, macro yield charts, and coordinates recording & upload.
Official Lodgement Email: Transmitted to wangyr@pbcsf.tsinghua.edu.cn attaching Pitch Deck PDF, Project Spec PDF, GitHub repo URL, 3-minute
video demo URL, and team passport scans (≥ 60% non-Chinese).
 Tec-C 4-Person Engineering Roadmap & Technical Workstreams. Prepared for the Shenzhen International FinTech Competition (FinTechathon 2026).
Tec-C | 4-Person Engineering Roadmap & Technical Workstreams (Topic F)
Page 4 of 4
TEC-C 4-PERSON ROADMAP | SHENZHEN FINTECHATHON 2026 | TSINGHUA PBCSF & WEBANK

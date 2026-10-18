# Tec C How It Works Guide
> **Source PDF Document**: [`Tec-C_How_It_Works_Guide.pdf`](../09_reference_whitepapers/Tec-C_How_It_Works_Guide.pdf)  
> **Pages**: 6  
> **Transcribed & Documented for**: Tec-C Technical Documentation Suite

---

<!-- Page 1 -->

Page 1 of 6
TSINGHUA PBCSF & WEBANK • FINTECHATHON 2026 • TOPIC F: AGENT WALLET
Tec-C: Complete System, UI Architecture & Operational Guide
The Autonomous Corporate Expense Card for Web3 AI Agents with Cryptographic Safety Invariants
The Big Picture: Traditional trading bots require your master private keys, meaning one prompt injection or smart contract bug can
drain 100% of your funds. Tec-C (Tethered Expense Corporate Card) gives the AI a policy-tethered corporate card: it trades
autonomously 24/7 inside a user-configured daily leash, but is mathematically blocked on-chain from exceeding limits, touching
unvetted tokens, or withdrawing your treasury.
Tec-C Vault $48,210 +1.2% Tether $420 / $1,000 Brain Heartbeat 3h ago Biometric Window Locked + Deposit
⇪  Withdraw (FaceID)
01 The 3 Pillars of Tec-C
1. Non-Custodial Agent Wallet
The Smart Safe. Built on ERC-7579 & ERC-
4337. Assets stay in the smart vault. The AI
never sees or holds your master key--it
holds an ephemeral session key restricted by
bytecode hooks.
2. Mathematical Leash
The Hard Spending Boundary. Enforced
on-chain by TetherGuardHook.sol. Daily
limits are converted to 8-decimal USD via
Chainlink price feeds. The AI physically
cannot exceed the limit.
3. Mobile Virtual Session
The Master Remote Key. Runs on your
laptop, but connects securely to your
smartphone via Cloudflare tunnel. Monitor
positions and approve breakout trades via
FaceID from any coffee shop.
02 The Core Problem Solved: Autonomy vs. Safety
Feature / Risk Traditional Trading Bots Standard Hardware Wallet Tec-C Autonomous Vault
Autonomous 24/7
Trading ✔  Full autonomy ✖  Zero (Manual click foreverything) ✔  Full autonomy inside your limit
Catastrophic Hack Risk ✖  High (API keys can drain100%) ✔  Low (Keys kept offline) ✔  Zero (Capped by strict on-chain leash)
Daily Limit Tuning ✖  Unbounded ✖  Not applicable ✔  User configures initial limit & opt-inelasticity
Multi-Chain Vault
Operations ✖  Fragmented / complex ✖  Manual network switching ✔  Multi-chain deposit & Biometricwithdrawal
Privacy Before Cloud AI ✖  Leaks full balances &addresses ✔  N/A ✔  Privacy Sieve (Normalized 1,000privacy units)
03 Dynamic Elasticity: The Accuracy Feedback Loop
🔄  Personalized Limits: AI Earns or Loses Autonomy Based on Accuracy Onboarding Consent
During onboarding, you choose your starting daily allowance (e.g. $1,000/day). You are then asked: "Do you want your limit to be personalized
and adaptively influenced by AI accuracy?"
✔  High Accuracy (Trust Rewards): When the AI makes profitable
trades and you ratify them in the Morning Review, the vault awards
a step-up (up to +10% per day max) towards your configured
ceiling.
✖  Mistakes (Immediate Penalties): If the AI enters a bad pool,
flagging it in Morning Review contracts the daily limit by -20%.
Adding a penalty note contracts it by -10%. Trust is lost 7x faster
than it is gained!
Tec-C System Guide • Page 1 of 6 Engineered for Maximum Autonomy & Absolute Security

---

<!-- Page 2 -->

Page 2 of 6
04 Screen 1: Home & Command Center
The central hub where you submit structured investment mandates, monitor the live pipeline, and toggle the continuous background
arbitrage engine.
1. New Command Composer Interactive
5 structured building blocks translate your intent into a typed mathematical
mandate (no prompt injection vectors):
1 · Action: Find opportunities | Invest | Stake | Swap | Rebalance |
Reduce risk | Exit position | Park idle cash
2 · Market: Crypto (Ethereum) | Chinese market (FISCO BCOS) |
Commodities (Arbitrum One) | Any (All enabled)
3 · Asset / Scope: ETH | stETH | rETH | USDC | All in market
4 · Capital Amount: 5% | 10% | 25% | Custom Slider (e.g. 10% = $4,821
· uses $482 of remaining Tether)
5 · Risk Tier: Tier 1 (Core) | Tier 2 (Growth) | Tier 3
(Unrestricted - Locked)
"Stake ETH and stETH in Crypto, using 10% of capital, Tier 2." ➔  [Submit to Brain]
2. Live Pipeline Tracker Request #0412
● Command: Submitted (0.2 s)
● Brain Analysis: 3 options discovered (1.4 s)
◐ Ratings:
• News & Sentiment: Done (+0.71)
• Econometrics & Liquidity: Running
• Injection Defense: Waiting
○ Brain Decision: Awaiting synthesis
○ Executor: Session key dispatch
○ On-Chain Guard: Tether check
○ Morning Review: Pending
⚡  Dedicated Background Arbitrage Engine (PegGuard) Independent Toggle Switch
Arbitrage is NOT a one-off trade command inside the composer. It is a standalone, persistent toggle switch located outside the command
box:
When ENABLED [ON]: The bot operates 24/7 in the background via POST /api/arbitrage/toggle, continuously scanning the 24-asset
catalog across 4 categories (Class B Fiat Stablecoins, Class A LSTs/LRTs, Class A Wrapped BTC, Class B RWAs) spanning Ethereum L1,
Arbitrum One L2, and FISCO BCOS. Features Stateful Unprofitable Watermark Memory to prevent wasting gas on stagnant prices.
When DISABLED [OFF]: The arbitrage scanner is completely discarded and idle, conserving gas and network activity until re-enabled.
05 Multi-Chain Vault Operations & Biometric Security
📥  Multi-Chain Deposit All Supported Networks
Deposit funds seamlessly on any available connected chain:
• Ethereum Mainnet & Arbitrum One (ETH, USDC, USDT)
• FISCO BCOS Consortium Chain (e-CNY, enterprise tokens)
• Optimism & Polygon (DeFi collateral)
Deposits credit your normalized 8-decimal USD vault balance via
Chainlink price feeds.
📤  Biometric Withdrawal FaceID / TouchID Required
Strict Security Invariant: The AI session key has ZERO authority to
withdraw funds to external addresses.
• Withdrawing capital to an external address strictly requires
hardware biometric verification (FaceID / TouchID via WebAuthn
NIST P-256).
• Even if the AI agent server is fully breached, the user's treasury can
never be drained.
Tec-C System Guide • Page 2 of 6 Screen 1: Home & Command Center

---

<!-- Page 3 -->

Page 3 of 6
06 Screen 2: Opportunities & Bounded AI Rating
When a command is submitted, the AI Brain explores multiple paths and presents a transparent, graded comparison with full risk
breakdowns.
Zone A · Candidates for Request #0412 (Stake ETH / stETH, 10% Capital)
Option A · Stake ETH on
Lido
Chosen
70%
Crypto · Staking · 2.0 ETH · $4,821
News: +0.71 | Econ: 0.64 | Injection: Pass
0.68 Weighted Score
Option B · Supply ETH on
Aave
Chosen
30%
Crypto · Lending · 2.0 ETH · $4,821
News: +0.55 | Econ: 0.70 | Injection: Pass
0.61 Weighted Score
Zone B · Deep Rating Breakdown for Option A (Lido Staking)
1. News & NLP
Sentiment
+0.71
Positive
• FinBERT Sentiment: Scores from -1 (Panic)
to +1 (Euphoria). Current: +0.71.
• Recent Headlines: 4 articles processed in
last 9h (3 Positive, 1 Neutral).
• Vault Sovereignty Invariant: News informs
Brain trade sizing only; it can never freeze or
halt the smart vault.
2. Econometrics &
Liquidity Acceptable
• Tail Risk (CVaR): 95% CVaR is -3.1% | 99%
CVaR is -5.4%.
• Slippage Model: Modeled curve estimates
0.08% slippage for a $4,821 execution.
• Liquidity Comparison:
Staking: 3.4%
APY
CVaR: -3.1% Slip: 0.08%
Lending: 2.6%
APY
CVaR: -2.4% Slip: 0.02%
3. Prompt-Injection Defense Pass
• ✔ Whitelist: Target contract verified.
• ✔ Honeypot Test: Clean token bytecode.
• ✔ Contract Age: 4.2 years battle-tested.
• ✔ Amount Check: Matches command
mandate.
• ✔ Instruction Scan: Zero injection payloads.
Zone C · Brain Decision & Autonomous Synthesis
Agent Weights (Adjustable in Settings)
News 30% Econometrics 45% Injection 25%
Synthesis Reason: Options A and B both pass hard filters with close
scores (0.68 vs 0.61). The Brain chooses a portfolio diversification split.
Execution Outcome Autonomous
Split: A 70% ($3,375) · B 30% ($1,446)
Inside today's Tether Radius ($482 used of $580 left), so it executes
autonomously without requiring manual button clicks.
Other Possible Outcomes: Proceed with Single Best  • Do Nothing (Negative Edge)  • Needs Biometric Breakout (Approve / Reject)
Tec-C System Guide • Page 3 of 6 Screen 2: Opportunities & Bounded AI
Option C · Buy stETH on
DEX
Rejected
Crypto · Swap · 2.0 ETH · $4,821
News: +0.71 | Econ: 0.41 | Injection: Warn
0.44 Weighted Score

---

<!-- Page 4 -->

Page 4 of 6
07 Screen 3: Portfolio Holdings & Hourly Watchdog
Comprehensive multi-asset treasury monitoring combined with an automated hourly safety scanner.
Total Portfolio Valuation +1.2% in 24h
$48,210 +$574 Today
Multi-chain balances normalized to 8-decimal USD via Chainlink price feeds.
Asset Allocation 4 Sectors
■ Crypto: 52% ■ Chinese Mkt: 22%
■ Commodities: 16% ■ Arbitrage: 10%
Live Treasury Holdings
Asset Market / Chain Balance USD Value Share 24h P&L News Sentiment Health Status
stETH Crypto (Ethereum) 6.20 $14,933 31% +4.1% Positive (+0.71) ● OK
USDC Crypto (Arbitrum One) 10,200 $10,200 21% 0.0% Neutral (0.00) ● OK
PAXG Commodities (Arbitrum) 3.10 $7,720 16% +1.8% Neutral (+0.12) ● Watch
e-CNY MMF Chinese Market (FISCO BCOS) 10,600 $10,600 22% -0.6% Negative (-0.45) ● Re-evaluate
08 The Hourly Watchdog Engine
🛡  24-Hour Autonomous Health Scanner Next scan in 38m
The Watchdog runs automatically every 60 minutes via /trigger_hourly_monitor across all held positions. It inspects on-chain pool depth,
oracle feeds, and financial news signals:
●●●●●●●●●●●●●●● Clean Scans (22) ● Market Warning (1) ● Negative News Alert (1)
Active Watchdog Alert: e-CNY MMF · negative news detected ➔  Brain triggered a risk-reduction proposal to de-risk 10% of position into USDC
collateral.
Tec-C System Guide • Page 4 of 6 Screen 3: Portfolio & Watchdog

---

<!-- Page 5 -->

Page 5 of 6
09 Screen 4: Morning Review & Adaptive Learning
Every morning, you spend 15 seconds reviewing what the AI traded while you were asleep. This is where you directly reward, correct,
and train your AI.
Overnight Trades: 5 Capital Moved: $1,240 Reviewed: 2 of 5 Ratify the Rest
📈  Like Streak Toward Radius Increase 3 of 5 Approved · Eligible for +10% Step-Up
Trade #1: Stake 0.4 ETH on Lido
Executed at 02:14 UTC · Crypto Market · $964 Value
Pending Review
Slippage: 0.08% (est. 0.10%) P&L Now: +$3.20 Tx Hash: 0x9a4f...e1c8
👍  Like & Ratify 👎  Flag for Revert (-20%) 📝  Note
Your Note to the Brain (Opens on " 📝  Note" click): 12 / 25 words
"Lido staking is approved, but prefer rocket pool (rETH) when yield difference is under 0.2%."
⚠  Penalize Autonomy (-10%) Sent to AI Brain memory ➔ Send Note
How AI Brain Acts: Notes are transmitted to the Brain's learning engine (tecc_brain.learning.notes). The AI updates its internal protocol affinity,
refines cost multipliers, and initiates proactive portfolio adjustments or rebalancing if required.
Swap 500 USDC to PAXG · 03:40 UTC · Commodities Pending Review ⌄
Supply 1 ETH to Aave v3 · 01:02 UTC · Crypto ✔  Ratified · Allowance Restored
Tec-C System Guide • Page 5 of 6 Screen 4: Morning Review

---

<!-- Page 6 -->

Page 6 of 6
10 Real-World Scenarios & Everyday Life
How all systems operate together during regular days, high-value opportunities, and market crises:
Scenario A: Silent Daily Yield Harvesting 100% Autonomous
Situation: You set an initial daily allowance of $1,000 for your vault.
AI Discovery: The AI Brain spots Compound v3 offering an 11.2% lending yield on USDC.
Execution: The AI deposits $800 into Compound. Because $800 is under your $1,000 leash, it executes silently on-chain. You wake up with extra
yield without having to click a button.
Scenario B: The High-Value Breakout Trade Biometric FaceID Required
Situation: The AI Brain spots a flash $4,500 stablecoin arbitrage capturing a $120 net profit in 30 seconds.
What Happens: The smart contract detects that $4,500 exceeds your $1,000 daily leash. It blocks autonomous execution and buzzes your
smartphone.
User Action: You glance at the notification card, verify the profit, scan FaceID. The 5-minute window opens and the trade completes instantly.
Scenario C: Dynamic Elasticity in Action Adaptive Learning
Starting Point: You configure a $1,000 daily limit with Dynamic Elasticity enabled (Hard Ceiling: $2,500).
Week 1 (High Accuracy): The AI executes 5 successful yield trades. You hit "Ratify" in Morning Review. The vault rewards it by +10%/day,
expanding allowance to $1,460.
Week 2 (Correction): The AI enters an asset you dislike. You flag it. The vault penalizes it by -20%, shrinking the limit down to $1,168.
Scenario D: PegGuard Crisis Circuit-Breaker Depeg Defense
Situation: You hold 6,000 units of a synthetic coin. Breaking news indicates backing reserve distress; price slips to $0.982.
Automated Defense: Within seconds, PegGuard activates its emergency circuit-breaker and swaps the 6,000 coins into native USDC. An hour later
the coin collapses to $0.40. Your capital was saved.
Scenario E: Remote Coffee Shop Access (Virtual Session) Encrypted Tunnel
Setup: You click "Create Virtual Session" on your home PC and scan the QR code with your iPhone.
Experience: An encrypted tunnel connects to your phone browser. Authenticated via phone FaceID, you steer risk, monitor trades, and approve
breakouts all day without opening ports.
11 Summary of Unbreakable Security Invariants
1. AI can NEVER withdraw funds: External transfers strictly require
hardware FaceID.
2. AI can NEVER exceed daily limit: Leash enforced on-chain via
Chainlink USD feeds.
3. AI can NEVER touch unwhitelisted tokens: Bytecode whitelist blocks
fake tokens.
4. Trust is lost 7x faster than gained: -20% penalty on flag vs. max
+10% daily growth cap.
Tec-C System Guide • Page 6 of 6 Complete Architecture, UI Screens & Operational Flows
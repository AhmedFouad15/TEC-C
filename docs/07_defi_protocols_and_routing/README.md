# Tec-C: Verified DeFi Protocols & Execution Registry

This document catalogs the verified DeFi protocols, smart contracts, function selectors, and risk tiers integrated into the Tec-C multi-market executor.

All protocol configurations are stored in [`shared/defi_protocols.json`](..\../shared/defi_protocols.json).

---

## 1. Supported DeFi Protocol Matrix

| Protocol | Category | Supported Chains | Risk Tier | Primary Operation | Target Contract | Selector |
|---|---|---|---|---|---|---|
| **Lido Liquid Staking** | Liquid Staking | Ethereum Mainnet (`1`), Arbitrum One (`42161`) | **Tier 1 (Core)** | `submit(address)` / `wrap(uint256)` | `stETH` / `wstETH` | `0xa1903eab` / `0xea598cb0` |
| **Aave v3** | Lending & Yield | Ethereum Mainnet (`1`), Arbitrum One (`42161`) | **Tier 1 (Core)** | `supply(address,uint256,address,uint16)` | `Pool` | `0x617ba037` |
| **Curve Finance** | Stablecoin DEX / AMM | Ethereum Mainnet (`1`), Arbitrum One (`42161`) | **Tier 1 (Core)** | `exchange(int128,int128,uint256,uint256)` | `stETH/ETH Pool` | `0x3df02124` |
| **Uniswap v3** | Concentrated Liquidity | Ethereum Mainnet (`1`), Arbitrum One (`42161`) | **Tier 2 (Growth)** | `exactInputSingle(...)` | `SwapRouter` | `0x414bacae` |
| **Compound v3** | Institutional Lending | Ethereum Mainnet (`1`), Arbitrum One (`42161`) | **Tier 1 (Core)** | `supply(address,uint256)` | `cUSDCv3` | `0xf2b9fdb8` |
| **Paxos Gold (PAXG)** | RWA / Commodities | Arbitrum One (`42161`), Ethereum (`1`) | **Tier 2 (Growth)** | `transfer(address,uint256)` | `PAXG` | `0xa9059cbb` |
| **EigenLayer** | Restaking | Ethereum Mainnet (`1`) | **Tier 3 (Unrestricted)** | `depositIntoStrategy(address,address,uint256)` | `StrategyManager` | `0xeaa8a342` |
| **Shibor MMF** | Onshore Money Market | FISCO BCOS (`20200`) | **Tier 1 (Core)** | `deposit(uint256)` / `withdraw(uint256)` | `ShiborVault` | `0xb6b55f25` |

---

## 2. Risk Tier Guardrails & Whitelisting

Every protocol interaction is verified on-chain by [`TetherGuardHook.sol`](..\../contracts/src/hooks/TetherGuardHook.sol) before execution:

1. **Tier 1 (Core Capital Preservation)**:
   - Permitted: Stablecoins (USDC, USDT), native ETH, liquid staking derivatives (stETH), top money market funds (Aave, Compound, Shibor MMF).
   - Strict maximum daily tether radius ($500 standard).
2. **Tier 2 (Balanced Growth)**:
   - Permitted: Tier 1 assets plus tokenized commodities (PAXG gold) and concentrated DEX pools (Uniswap v3).
   - Dynamic elasticity enabled (radius can expand up to 10% per review cycle).
3. **Tier 3 (Unrestricted / Arbitrage)**:
   - Permitted: Cross-market arbitrage and complex restaking strategies (EigenLayer).
   - Requires explicit biometric FaceID approval for breakout operations exceeding the tether ceiling.

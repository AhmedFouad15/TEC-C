# Part 7: DeFi Venues & Routing Matrix

This document provides the complete routing matrix, contract targets, function signatures, and risk tiers for all verified DeFi protocols integrated across Ethereum, Arbitrum, Base, and FISCO BCOS.

---

## 1. Verified Protocol Registry & Risk Tiers

| Protocol | Risk Tier | Primary Markets | Supported Action | Target Asset | Whitelist Check |
|---|---|---|---|---|---|
| **Lido Finance** | Tier 1 (Core) | Ethereum L1 | `STAKE` | ETH $\rightarrow$ stETH | Enforced |
| **Aave v3** | Tier 1 (Core) | Ethereum, Arbitrum | `SUPPLY`, `WITHDRAW` | USDC, USDT, ETH | Enforced |
| **Uniswap v3** | Tier 2 (Growth) | Ethereum, Arbitrum, Base | `SWAP`, `EXACT_INPUT` | USDC, ETH, DAI | Enforced |
| **Curve Finance** | Tier 2 (Growth) | Ethereum L1 | `EXCHANGE`, `ADD_LIQ` | 3pool (USDC/USDT/DAI) | Enforced |
| **Compound v3** | Tier 1 (Core) | Ethereum, Arbitrum | `SUPPLY` | USDC, ETH | Enforced |
| **Shibor MMF** | Tier 1 (Core) | FISCO BCOS | `DEPOSIT`, `YIELD` | Institutional CNY/USDT Repo | Enforced |
| **Paxos Gold (PAXG)** | Tier 1 (Core) | Arbitrum One | `TRANSFER`, `VAULT` | Tokenized Physical Gold | Enforced |
| **EigenLayer** | Tier 2 (Growth) | Ethereum L1 | `RESTAKE` | stETH, rETH | Enforced |

---

## 2. On-Chain Calldata Execution Encoding

The Brain constructs standardized execution calldata signed by the ephemeral session key:

```python
# 1. Staking on Lido
execution_calldata(venue, wei, protocol.encode("stake"))

# 2. Supplying to Aave v3 Pool
execution_calldata(aave_pool, 0, aave_pool.encode("supply", asset, amount, on_behalf_of, 0))

# 3. Swapping on Uniswap v3 / Curve
execution_calldata(router, 0, router.encode("exactInputSingle", params))
```

All targets must be pre-registered in `TetherGuardHook.setTargetWhitelist(venue, true)` by the passkey root owner; unwhitelisted targets immediately revert at the pre-check hook level.

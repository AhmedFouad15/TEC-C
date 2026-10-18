# Part 3: Chainlink Oracles & Multi-Chain Pricing Catalog

This document details the pricing architectures, decentralized Chainlink oracle aggregators, and free market data feeds integrated into Tec-C.

---

## 1. Multi-Chain Chainlink Oracle Architecture

Tec-C normalizes all asset values to a unified 8-decimal USD baseline matching the on-chain `TetherGuardHook` metering precision (`USD × 1e8`).

### Ethereum / Sepolia Oracles
| Asset | Pair | Decimals | Deviation Threshold | Heartbeat | Feed Address |
|---|---|---|---|---|---|
| **ETH** | ETH/USD | 8 | 0.5% | 3600s | `0x694AA1769357215DE4FAC081bf1f309aDC325306` |
| **USDC** | USDC/USD | 8 | 0.25% | 86400s | `0xA2F78ab2355fe2f984D808B5CeE7FD0A93D5270E` |
| **USDT** | USDT/USD | 8 | 0.25% | 86400s | `0xA2F78ab2355fe2f984D808B5CeE7FD0A93D5270E` |
| **stETH** | stETH/ETH | 18 | 0.5% | 86400s | `0x86392dC19c0b719886221c78AB11eb8Cf5c52812` |
| **PAXG** | PAXG/USD | 8 | 0.5% | 3600s | `0x0CBE80946b5275e60824b2F36d390a4242dBEb54` |

### Arbitrum One / Sepolia Oracles
| Asset | Pair | Decimals | Heartbeat | Feed Address |
|---|---|---|---|---|
| **ETH** | ETH/USD | 8 | 3600s | `0xd30e2101a97dcbAeBCBC04F14C3f624E67A35165` |
| **PAXG** | PAXG/USD | 8 | 3600s | `0x48f5F8F617b07E4fB14b8aF887cbeB321f64fAc4` |
| **USDC** | USDC/USD | 8 | 86400s | `0x0153002d20B96532C639313c2d54c3dA0910B30E` |

---

## 2. In-Memory Mock Aggregator for Deterministic Local Testing

To enable fast offline testing, [`contracts/test/mocks/MockChainlinkOracle.sol`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/contracts/test/mocks/MockChainlinkOracle.sol) implements the full Chainlink `AggregatorV3Interface`:

```solidity
contract MockChainlinkOracle is AggregatorV3Interface {
    uint8 public override decimals;
    string public override description;
    uint256 public override version = 1;
    int256 private _price;
    uint256 private _updatedAt;

    function setPrice(int256 price) external;
    function latestRoundData() external view returns (
        uint80 roundId, int256 answer, uint256 startedAt, uint256 updatedAt, uint80 answeredInRound
    );
}
```

---

## 3. Stale Oracle Price Reversion Invariant

`TetherGuardHook.sol` enforces that any oracle feed with an `updatedAt` timestamp older than 24 hours strictly reverts with `StaleOraclePrice(token, updatedAt)`, protecting against oracle freeze attacks during flash crashes.

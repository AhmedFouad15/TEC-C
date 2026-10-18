# Tec-C: Market Data Feeds & Free vs Enterprise API Catalog

> **Core Philosophy**: **Zero Mandatory Cost / 100% Free Fallback**  
> Tec-C is architected so that any institution, researcher, or evaluator can run and test the full multi-agent pipeline without purchasing institutional data subscriptions or requiring paid API keys.

---

## 1. Does Tec-C Require Paid External APIs?

**No.**  
Tec-C operates under a multi-tier data feed model:
1. **Tier 1 (Default: Completely Free & Live)**: Connects to public, open decentralized oracles and REST endpoints requiring **$0.00 and no API keys**.
2. **Tier 2 (Offline Hermetic Fallback)**: If network connectivity is lost, Tec-C falls back instantly to a bundled, mathematically consistent demo snapshot (`SnapshotSource("demo")`), ensuring tests and demonstrations never crash or hang.
3. **Tier 3 (Institutional Reference Catalog)**: Documents enterprise feeds for institutional production deployments and provides concrete, zero-cost open alternatives.

---

## 2. Integrated Free Market Data Feeds ($0.00 / No API Key)

These feeds are actively integrated in [`agent/tecc_brain/market/live_feed.py`](..\../agent/tecc_brain/market/live_feed.py):

| Feed Name | Provider | Cost | Auth Required | Assets / Metrics | Mechanism |
|---|---|---|---|---|---|
| **Chainlink On-Chain Feeds** | Chainlink Decentralized Oracle Network | **$0.00** | None | ETH/USD, BTC/USD, USDC/USD, USDT/USD, PAXG/USD, stETH/USD | `eth_call latestRoundData()` on public Arbitrum One / Ethereum RPC endpoints |
| **DeFiLlama Public API** | DeFiLlama Open Project | **$0.00** | None | Multi-chain token prices, Lido APY, Aave v3 yields, Curve pool TVLs | REST JSON: `https://coins.llama.fi` & `https://yields.llama.fi` |
| **Binance Public Spot Tickers** | Binance Public REST | **$0.00** | None | ETHUSDT, BTCUSDT, PAXGUSDT, USDCUSDT spot prices | REST JSON: `https://api.binance.com/api/v3/ticker/price` |
| **Fear & Greed Index** | Alternative.me API | **$0.00** | None | Crypto Market Sentiment Index | REST JSON: `https://api.alternative.me/fgt/` |

---

## 3. Paid Enterprise Feeds vs Free Alternatives

While tier-1 institutional trading desks utilize multi-thousand dollar subscription feeds, Tec-C maps every enterprise feed to an accessible, zero-cost alternative:

### Summary Comparison Table

| Enterprise / Paid Feed | Typical Cost | Institutional Use Case | Zero-Cost Free Alternative | Free Endpoint / Method | Trade-off / Limitation |
|---|---|---|---|---|---|
| **Bloomberg Terminal / B-PIPE** | ~$2,500 / month ($30,000 / year) | Macro fixed income, Shibor fixings, SOFR, FX basis | **FRED Public API & Chinamoney Public Table** | `https://api.stlouisfed.org` / Chinamoney fixing table | Daily fixing & 15-minute delayed quotes rather than sub-second tick feed; sufficient for daily Shibor hurdle rate calibrations. |
| **Kaiko Enterprise Tick & Depth** | $10,000 – $50,000 / year | Regulatory reference rates, L2/L3 order book market depth, slippage modeling | **Binance & Coinbase Public L2 Depth API** | `https://api.binance.com/api/v3/depth?symbol=ETHUSDT&limit=100` | Single dominant exchange orderbook snapshot rather than cross-CEX composite; accurately detects orderbook thinning and slippage. |
| **Amberdata Institutional API** | $15,000 – $35,000 / year | Real-time DEX swap telemetry, mempool event logs, pool reserve metrics | **DexScreener API & The Graph Subgraphs** | `https://api.dexscreener.com/latest/dex/tokens/` | Block-indexed telemetry (1–2 block latency) rather than raw mempool socket feeds; captures pool liquidity and effective swap impact accurately. |
| **CoinAPI Enterprise** | $79 – $599+ / month | Normalized WebSocket streaming across 300+ centralized exchanges | **CCXT Open-Source Engine & Direct WebSockets** | Open-source Python `ccxt` package / `wss://stream.binance.com:9443/ws` | Self-managed connection pooling rather than a commercial SaaS aggregator; zero recurring subscription fee. |
| **Nansen Alpha / Query** | $1,000 – $3,000 / month | Institutional wallet labeling, smart money flow detection, exchange reserves | **DeFiLlama Protocol Treasuries & Etherscan Free Tier** | `https://api.llama.fi` / `https://api.etherscan.io` | Protocol-level treasury tracking rather than proprietary entity address clustering; tracks smart money reserves and bridge flows accurately. |

---

## 4. Automatic Caching & Fault-Tolerant Fallback

To prevent remote network throttling or cloud endpoint outages from impacting transaction execution:
1. **Cache TTL (15.0 seconds)**: Responses from public APIs are cached in-memory. Consecutive execution requests within the TTL window share the cached snapshot, preventing IP rate-limiting.
2. **Strict Timeouts (3.5 seconds)**: Any network call that takes longer than 3.5 seconds is aborted.
3. **Hermetic Fallback**: If all live remote data sources fail, the pipeline immediately yields `fallback:snapshot:demo`, preserving full functional responsiveness.

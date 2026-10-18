# Tec-C: Multi-Chain Deployments & FISCO BCOS Cluster Architecture

Tec-C routes transactions across three distinct production/testnet blockchain environments plus a local development chain:

```
                               ┌────────────────────────────────────────────────┐
                               │           Tec-C Multi-Market Router            │
                               └───────┬──────────────┬──────────────┬──────────┘
                                       │              │              │
                   ┌───────────────────┘              │              └───────────────────┐
                   ▼                                  ▼                                  ▼
      ┌─────────────────────────┐        ┌─────────────────────────┐        ┌─────────────────────────┐
      │     Crypto Market       │        │   Commodities Market    │        │     Onshore Market      │
      │   Ethereum Sepolia      │        │      Arbitrum One       │        │  FISCO BCOS Consortium  │
      │    Chain ID: 11155111   │        │     Chain ID: 42161     │        │     Chain ID: 20200     │
      │  Gas: Standard EIP-1559 │        │  Gas: L2 Rollup Sequencer│        │  Gas: $0.00 Enterprise  │
      └─────────────────────────┘        └─────────────────────────┘        └─────────────────────────┘
```

---

## 1. Multi-Chain Network Specifications

| Market | Network | Chain ID | RPC Protocol | Gas Model | Deployed State File | Primary Asset / Venues |
|---|---|---|---|---|---|---|
| **Crypto** | Ethereum Sepolia / L1 | `11155111` / `1` | HTTPS JSON-RPC | EIP-1559 | [`shared/contracts.sepolia.json`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/shared/contracts.sepolia.json) | ETH, USDC, Lido stETH, Aave v3 |
| **Commodities** | Arbitrum One / Sepolia | `42161` / `421614` | HTTPS JSON-RPC | Nitro L2 | [`shared/contracts.arbitrum.json`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/shared/contracts.arbitrum.json) | PAXG (Tokenized Gold), USDC |
| **Onshore** | FISCO BCOS (WeBank) | `20200` (`0x4ee8`) | Web3 JSON-RPC (`:8555`) | Zero-Gas ($0.00) | [`shared/contracts.fisco.json`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/shared/contracts.fisco.json) | Shibor MMF, Privacy Audit Anchors |
| **Local Dev** | Anvil Local Node | `31337` | HTTP JSON-RPC (`:8545`) | Instant Mine | `agent/.state/local_deployment.json` | MockERC20, MockFeeds, All Venues |

---

## 2. FISCO BCOS 4-Node Testnet Cluster (Section 7)

For the Onshore Market and WeBank consortium chain evaluation, Tec-C runs an official FISCO BCOS testnet cluster:

- **Version**: Official FISCO BCOS release `v3.17.1`.
- **Topology**: 4-node PBFT consensus cluster (`node0`, `node1`, `node2`, `node3`) located in WSL Ubuntu at `/home/ahmed/fisco/nodes/127.0.0.1/`.
- **Web3 JSON-RPC Interface**: Enabled on `node0` via `[web3_rpc]` in `config.ini`:
  - `listen_ip = 0.0.0.0`
  - `listen_port = 8555`
  - `thread_count = 8`
- **Native Gas Sponsorship**: Consortium chains utilize quota-based enterprise sponsorship; transactions are executed with `gasPrice = 0` ($0.00 cost to cardholders).

---

## 3. The EVM Millisecond Timestamp Nuance

### Discovery & Problem
In standard Ethereum EVM environments, the `TIMESTAMP` opcode returns epoch time in **seconds** (10 digits, e.g., `1,792,316,505`).  
In FISCO BCOS, the internal EVM implementation returns block timestamps in **milliseconds** (13 digits, e.g., `1,792,316,505,000`).

Any smart contract or oracle that blindly compares seconds with `block.timestamp` without scale normalization fails on FISCO BCOS:
- E.g., `block.timestamp - updatedAt > 1 days` (where `1 days = 86400` in Solidity): on a millisecond EVM, `86400` milliseconds is only **86.4 seconds**. After 1.5 minutes, all oracle checks revert with `StaleOraclePrice`.

### The Solution: Cross-EVM Scale Normalization
Tec-C solves this at both the smart contract and executor layers:
1. **Timestamp Normalization in Contracts**:
   ```solidity
   // TetherGuardHook.sol
   uint256 curTime = block.timestamp > 1e11 ? block.timestamp / 1000 : block.timestamp;
   uint256 updTime = updatedAt > 1e11 ? updatedAt / 1000 : updatedAt;
   if (curTime > updTime && curTime - updTime > 1 days) {
       revert StaleOraclePrice(token, updatedAt);
   }

   // SessionKeyValidator.sol
   uint256 currentTimestamp = block.timestamp > 1e11 ? block.timestamp / 1000 : block.timestamp;
   if (currentTimestamp < sk.validAfter || currentTimestamp > sk.validUntil) return EIP1271_FAILED;
   ```
   *The threshold `1e11` cleanly distinguishes millisecond EVMs (13 digits) from standard EVMs (which will not reach `1e11` until the year 5138 AD).*

2. **Paris EVM Bytecode Compilation**:
   FISCO BCOS supports the Paris EVM specification. Contracts are compiled with:
   `forge build --evm-version paris --out out-paris`

---

## 4. Automated Node Lifecycle Supervisor

### The WSL 2 Idle Timeout Challenge
In Windows 11 WSL 2, background processes launched without an interactive console session are terminated by the Windows hypervisor after a 15-second idle timeout.

### The Supervisor Architecture
Tec-C implements an automated lifecycle manager in [`agent/tecc_brain/onchain/fisco_node.py`](file:///C:/Users/Ahmed/OneDrive/Desktop/CHINA/agent/tecc_brain/onchain/fisco_node.py):

```
[Application Startup] (FastAPI lifespan / Runner)
         │
         ▼
[is_fisco_node_running()] ──Yes──▶ (Ready; proceed to transactions)
         │ No
         ▼
[ensure_fisco_node_running()]
         │
         ├─▶ Launches persistent supervisor process:
         │   `wsl -u root -d Ubuntu -- bash /home/ahmed/fisco/run_cluster.sh`
         │
         ├─▶ Writes Windows PID to `agent/.state/fisco_cluster.pid`
         │
         └─▶ Polls `eth_chainId` on `http://127.0.0.1:8555` until `0x4ee8` returns (Chain 20200)
         │
         ▼
[Application Shutdown]
         │
         ▼
[stop_fisco_node()]
         ├─▶ Terminates supervisor process & Windows PID
         ├─▶ Runs `/home/ahmed/fisco/nodes/127.0.0.1/stop_all.sh` in WSL
         └─▶ Releases all network ports and process memory cleanly
```

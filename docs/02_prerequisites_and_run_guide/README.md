# Tec-C: Prerequisites & Complete Run Guide

This document details all software dependencies, environment setups, and exact commands required to run the full Tec-C system end-to-end.

---

## 1. System Requirements & Prerequisites

### Core Software Dependencies

| Component | Minimum Version | Purpose | Installation Command / Link |
|---|---|---|---|
| **Python** | 3.10+ (Recommended: 3.11–3.13) | Brain agent, LangGraph pipeline, Web3 executors | `python --version` ([python.org](https://www.python.org/)) |
| **Foundry / Forge** | 0.2.0+ (Solc 0.8.24) | Smart contract compiling, fuzzing, testing | `curl -L https://foundry.paradigm.xyz \| bash; foundryup` |
| **WSL 2 (Ubuntu)** | Windows 10/11 only | Runs official 4-node FISCO BCOS testnet cluster | `wsl --install -d Ubuntu` |
| **Cloudflare Tunnel** | `cloudflared` (Optional for Mobile pairing) | Exposes Mobile Gateway over free HTTPS tunnel | `winget install Cloudflare.cloudflared` |
| **Git** | 2.30+ | Version control & submodule tracking | `git --version` |

---

## 2. Environment Setup

### A. Python Virtual Environment

From the `agent/` directory:

```powershell
cd agent

# 1. Create virtual environment
python -m venv .venv

# 2. Activate virtual environment
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# 3. Install core dependencies and development tools
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Install tecc_brain in editable mode
pip install -e .
```

### B. Smart Contract Toolchain (Foundry)

From the `contracts/` directory:

```powershell
cd contracts

# Install dependencies (forge-std, solady, etc.)
forge install

# Build smart contracts (Paris EVM compatible artifacts for FISCO BCOS)
forge build
forge build --evm-version paris --out out-paris
```

---

## 3. Running the Verification Test Suites

Tec-C maintains **100% test pass rate** across all components:

### A. Run Foundry Smart Contract Test Suite (167 Tests)

```powershell
cd contracts
forge test
```
*Executes unit tests, differential fuzzing (256 runs/test), EIP-7579 hook validations, WebAuthn P-256 precompile tests, and PrivacyAuditAnchor verification.*

### B. Verify EIP-170 Contract Bytecode Limits ($\le 24,576$ bytes)

```powershell
cd contracts
forge build --sizes
```
*Current measurements:*
- `PrivacyAuditAnchor`: **974 bytes** (23,602 byte headroom)
- `SessionKeyValidator`: **3,124 bytes** (21,452 byte headroom)
- `TecAccount`: **5,458 bytes** (19,118 byte headroom)
- `TecPaymaster`: **3,980 bytes** (20,596 byte headroom)
- `TetherGuardHook`: **24,418 bytes** (158 byte headroom $\le 24,576$)

### C. Run Python Agent & Risk Engine Test Suite (622 Tests)

```powershell
cd agent
.\.venv\Scripts\pytest
```
*Verifies all 622 tests covering prompt firewall, Bayesian profile learning, NLP Sentinel, PegGuard 5-layer arbitrage, multi-market executors, slippage recovery, and FISCO BCOS node lifecycle.*

---

## 4. Launching the Application

### Option 1: Dual Server Virtual Session (Recommended for Full Stack)

Runs the Admin App and the Mobile Pairing Gateway concurrently:

```powershell
cd agent
.\.venv\Scripts\python -m tecc_brain.virtual_session.runner
```
- **Admin App**: Listens on `http://127.0.0.1:8000` (holds signing keys, never exposed).
- **Mobile Gateway**: Listens on `http://127.0.0.1:8001` (accepts incoming pairing requests).
- **Lifecycle**: If `TECC_NETWORK=fisco_bcos` or `TECC_AUTO_START_FISCO=1`, the local FISCO BCOS testnet cluster starts automatically upon launch and terminates cleanly upon shutdown.

### Option 2: Standalone FastAPI Backend

```powershell
cd agent
.\.venv\Scripts\uvicorn tecc_brain.app:app --host 127.0.0.1 --port 8000 --reload
```

---

## 5. Multi-Market Deployment & Smoke Transactions

Tec-C includes automated provisioning scripts for all supported networks:

### A. Local Anvil Testnet (Crypto Market)
```powershell
# 1. Start Anvil in a separate terminal:
anvil --port 8545

# 2. Deploy vault suite:
.\.venv\Scripts\python scripts/deploy_market_chain.py --network anvil --rpc http://127.0.0.1:8545

# 3. Execute real smoke deposit:
.\.venv\Scripts\python scripts/deploy_market_chain.py --network anvil --smoke 25 --smoke-venue aave_v3_usdc
```

### B. FISCO BCOS Consortium Testnet (Onshore Market)
```powershell
# Auto-starts the WSL cluster if stopped, executes deployment, provisions mandate, and saves state:
$env:TECC_DEPLOYER_KEY="0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
.\.venv\Scripts\python scripts/deploy_market_chain.py --network fisco_bcos --rpc http://127.0.0.1:8555 --no-native-coin

# Send real on-chain transaction:
.\.venv\Scripts\python scripts/deploy_market_chain.py --network fisco_bcos --smoke 25 --smoke-venue shibor_mmf
```

---

## 6. Manual FISCO BCOS Cluster Management

The cluster lifecycle is automatically handled by `tecc_brain.onchain.fisco_node`, but can also be controlled manually:

```powershell
# Probe node status:
.\.venv\Scripts\python -c "from tecc_brain.onchain.fisco_node import is_fisco_node_running; print(is_fisco_node_running())"

# Start the 4-node cluster in WSL:
.\.venv\Scripts\python -c "from tecc_brain.onchain.fisco_node import ensure_fisco_node_running; ensure_fisco_node_running()"

# Cleanly stop the cluster and release ports:
.\.venv\Scripts\python -c "from tecc_brain.onchain.fisco_node import stop_fisco_node; stop_fisco_node()"
```

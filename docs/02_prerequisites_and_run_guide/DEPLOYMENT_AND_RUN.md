# Part 2: Deployment & Operational Run Guide

This manual covers the step-by-step operational lifecycle for running, deploying, and validating the Tec-C system in development and simulated production environments.

---

## 1. System Requirements & Toolchain

| Component | Minimum Version | Recommended | Purpose |
|---|---|---|---|
| **Python** | 3.10.x | 3.11+ / 3.13+ | AI Brain, FastAPI, LangGraph state machine |
| **Foundry** | Latest (`forge 0.2.0+`) | Latest | Smart contract compilation, testing & fuzzing |
| **WSL 2** | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS | Local official FISCO BCOS v3.17.1 node cluster |
| **Node.js** | 18.x LTS | 20.x LTS | Optional UI / WebAuthn client tooling |
| **Cloudflared** | Latest | Latest | Quick-tunnel for biometric mobile passkey pairing |

---

## 2. Installation & Environment Setup

### A. Python Multi-Agent Virtual Environment
```bash
# Navigate to agent directory
cd agent

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux / macOS / WSL:
source .venv/bin/activate

# Install production and development dependencies
pip install -r requirements.txt -r requirements-dev.txt
```

### B. Smart Contracts & Foundry Toolchain
```bash
# Navigate to contracts directory
cd ../contracts

# Install Foundry dependencies & submodules
forge install

# Compile contracts and verify bytecode sizes
forge build --sizes
```

---

## 3. Test Suite Execution

### Running Smart Contract Tests (170 Tests)
```bash
cd contracts

# Run all test suites
forge test

# Run with verbose call tracing
forge test -vvv

# Verify code formatting against CI rules
forge fmt --check
```

### Running Python Multi-Agent Tests (637 Tests)
```bash
cd agent

# Run entire test suite
.\.venv\Scripts\python -m pytest tests/

# Run specific domain test suites
.\.venv\Scripts\python -m pytest tests/test_strictness_hierarchy.py -v
.\.venv\Scripts\python -m pytest tests/test_pegguard.py -v
.\.venv\Scripts\python -m pytest tests/test_slippage_recovery.py -v
.\.venv\Scripts\python -m pytest tests/test_fisco_node.py -v
```

---

## 4. Running the Dual-Server Architecture

Tec-C features a dual-server IPC runner separating administrative control from untrusted mobile biometric gateways:

```bash
# Start dual-server runner
cd agent
.\.venv\Scripts\python -m tecc_brain.virtual_session.runner
```

* **Admin Portal (FastAPI):** `http://127.0.0.1:8000` (Localhost-bound, high privilege).
* **Mobile Biometric Gateway:** `http://127.0.0.1:8001` (Exposed via Cloudflare Quick-Tunnel for biometric Face ID pairing).

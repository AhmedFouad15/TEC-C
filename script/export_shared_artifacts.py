import json
import os

def export_artifacts():
    base_dir = r"C:\Users\Ahmed\OneDrive\Desktop\CHINA"
    out_dir = os.path.join(base_dir, "contracts", "out")
    shared_file = os.path.join(base_dir, "shared", "contracts.json")
    desktop_file = r"C:\Users\Ahmed\Desktop\contracts.json"

    contract_map = {
        "TecAccount": os.path.join(out_dir, "TecAccount.sol", "TecAccount.json"),
        "TetherGuardHook": os.path.join(out_dir, "TetherGuardHook.sol", "TetherGuardHook.json"),
        "SessionKeyValidator": os.path.join(out_dir, "SessionKeyValidator.sol", "SessionKeyValidator.json"),
        "WebAuthnP256Validator": os.path.join(out_dir, "WebAuthnP256Validator.sol", "WebAuthnP256Validator.json"),
        "TecPaymaster": os.path.join(out_dir, "TecPaymaster.sol", "TecPaymaster.json"),
        "MockDeFiProtocol": os.path.join(out_dir, "MockDeFiProtocol.sol", "MockDeFiProtocol.json")
    }

    contracts_data = {
        "_meta": {
            "project": "Tec-C (Tethered Expense Corporate Card)",
            "competition": "Shenzhen International FinTech Competition (FinTechathon 2026)",
            "topic": "Topic F: Agent Wallet",
            "co_hosts": "Tsinghua University PBCSF & WeBank",
            "version": "1.0.0",
            "network": "Anvil / Ethereum Sepolia",
            "chainId": 31337
        },
        "defaultParameters": {
            "tetherRadiusDefaultWei": "500000000000000000", # 0.5 ETH (~$500 default tether radius)
            "maxSessionGasBudgetWei": "5000000000000000",   # 0.005 ETH anti-griefing limit
            "riskTiers": {
                "CONSERVATIVE": 1,
                "BALANCED": 2,
                "AGGRESSIVE": 3
            }
        },
        "deployedAddresses": {
            "EntryPoint": "0x0000000071727De22E5E9d8BAf0edAc6f37da032",
            "TetherGuardHook": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
            "SessionKeyValidator": "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512",
            "TecPaymaster": "0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0",
            "TecAccount": "0xCf7Ed3AccA5a467e9e704C703E8D87F634fB0Fc9",
            "MockLidoStaking": "0xDc64a140Aa3E981100a9becA4E685f962f0cF6C9",
            "MockCurveLP": "0x5FC8d32690cc91D4c39d9d3abcBD16989F875707"
        },
        "eip712": {
            "domain": {
                "name": "Tec-C Autonomous Agent Mandate",
                "version": "1",
                "chainId": 31337,
                "verifyingContract": "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"
            },
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"}
                ],
                "UserMandate": [
                    {"name": "action", "type": "string"},
                    {"name": "asset", "type": "string"},
                    {"name": "amount", "type": "uint256"},
                    {"name": "riskTier", "type": "uint8"},
                    {"name": "sessionKey", "type": "address"},
                    {"name": "validUntil", "type": "uint48"},
                    {"name": "nonce", "type": "uint256"}
                ]
            }
        },
        "contracts": {}
    }

    for name, artifact_path in contract_map.items():
        if os.path.exists(artifact_path):
            with open(artifact_path, "r", encoding="utf-8") as f:
                artifact = json.load(f)
                contracts_data["contracts"][name] = {
                    "abi": artifact.get("abi", []),
                    "bytecode": artifact.get("bytecode", {}).get("object", "")
                }
                print(f"Loaded ABI and bytecode for {name}")
        else:
            print(f"Warning: Artifact not found at {artifact_path}")

    # Write to shared folder
    os.makedirs(os.path.dirname(shared_file), exist_ok=True)
    with open(shared_file, "w", encoding="utf-8") as f:
        json.dump(contracts_data, f, indent=2)
    print(f"Exported shared contracts specification to: {shared_file}")

    # Mirror to Desktop
    with open(desktop_file, "w", encoding="utf-8") as f:
        json.dump(contracts_data, f, indent=2)
    print(f"Mirrored to Desktop at: {desktop_file}")

if __name__ == "__main__":
    export_artifacts()

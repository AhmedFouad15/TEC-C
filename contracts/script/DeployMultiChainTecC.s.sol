// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {TecAccount} from "../src/TecAccount.sol";
import {TetherGuardHook} from "../src/hooks/TetherGuardHook.sol";
import {SessionKeyValidator} from "../src/validators/SessionKeyValidator.sol";
import {TecPaymaster} from "../src/paymaster/TecPaymaster.sol";
import {MockDeFiProtocol} from "../test/mocks/MockDeFiProtocol.sol";

/**
 * @title DeployMultiChainTecCScript
 * @notice Automated multi-chain deployment script for the Tec-C Vault Suite across:
 *         1. Ethereum / Sepolia (Crypto Market) - ChainId: 1 / 11155111 / 31337
 *         2. Arbitrum One (Commodities Market) - ChainId: 42161 / 421614
 *         3. FISCO BCOS / WeBank (Chinese Market) - ChainId: 2026
 */
contract DeployMultiChainTecCScript is Script {
    function run() external {
        uint256 chainId = block.chainid;
        uint256 deployerPrivateKey =
            vm.envOr("PRIVATE_KEY", uint256(0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80));
        address deployer = vm.addr(deployerPrivateKey);
        address entryPoint = vm.envOr("ENTRYPOINT_ADDRESS", address(0x0000000071727De22E5E9d8BAf0edAc6f37da032));
        address rootOwner = vm.envOr("ROOT_OWNER", deployer);

        console.log("=== Deploying Tec-C Multi-Chain Vault ===");
        console.log("Active Chain ID:", chainId);
        console.log("Deployer Address:", deployer);
        console.log("Root Owner (Passkey / Biometric):", rootOwner);

        vm.startBroadcast(deployerPrivateKey);

        // 1. Core Security Hook
        TetherGuardHook hook = new TetherGuardHook();
        console.log("TetherGuardHook:", address(hook));

        // 2. Session Key Validator
        SessionKeyValidator validator = new SessionKeyValidator();
        console.log("SessionKeyValidator:", address(validator));

        // 3. Anti-Griefing Paymaster
        TecPaymaster paymaster = new TecPaymaster(entryPoint);
        console.log("TecPaymaster:", address(paymaster));

        // 4. TecAccount Master Smart Account
        TecAccount account = new TecAccount(entryPoint);
        account.initialize(rootOwner, address(hook), address(validator));
        console.log("TecAccount initialized:", address(account));

        // 5. Market-Specific Configuration
        if (chainId == 42161 || chainId == 421614) {
            // --- Arbitrum One / Arbitrum Sepolia (Commodities Market) ---
            console.log("Configuring Arbitrum One Commodities Market...");
            MockDeFiProtocol paxgGold = new MockDeFiProtocol();
            MockDeFiProtocol commodityLP = new MockDeFiProtocol();
            console.log("Mock PAXG Tokenized Gold:", address(paxgGold));
            console.log("Mock Commodity LP:", address(commodityLP));

            hook.initializeAccountPolicy(address(account), rootOwner, 0.5 ether, 2);
            hook.setTargetWhitelist(address(account), address(paxgGold), true, 1); // Tier 1 Conservative
            hook.setTargetWhitelist(address(account), address(commodityLP), true, 2); // Tier 2 Balanced
        } else if (chainId == 2026) {
            // --- FISCO BCOS / WeBank (Chinese Market) ---
            console.log("Configuring FISCO BCOS WeBank Consortium Chinese Market...");
            MockDeFiProtocol shiborMMF = new MockDeFiProtocol();
            console.log("Mock Shibor Treasury MMF:", address(shiborMMF));

            // Enterprise zero-gas quota policy setup
            hook.initializeAccountPolicy(address(account), rootOwner, 1.0 ether, 1);
            hook.setTargetWhitelist(address(account), address(shiborMMF), true, 1); // Tier 1 Conservative
        } else {
            // --- Ethereum / Sepolia / Anvil (Crypto Market) ---
            console.log("Configuring Ethereum / Sepolia Crypto Market...");
            MockDeFiProtocol lido = new MockDeFiProtocol();
            MockDeFiProtocol curveLP = new MockDeFiProtocol();
            console.log("Mock Lido Staking:", address(lido));
            console.log("Mock Curve LP:", address(curveLP));

            hook.initializeAccountPolicy(address(account), rootOwner, 0.2 ether, 2);
            hook.setTargetWhitelist(address(account), address(lido), true, 1);
            hook.setTargetWhitelist(address(account), address(curveLP), true, 2);
        }

        vm.stopBroadcast();
        console.log("=== Multi-Chain Deployment Completed Successfully ===");
    }
}

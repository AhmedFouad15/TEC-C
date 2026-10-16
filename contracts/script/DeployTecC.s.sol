// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {TecAccount} from "../src/TecAccount.sol";
import {TetherGuardHook} from "../src/hooks/TetherGuardHook.sol";
import {SessionKeyValidator} from "../src/validators/SessionKeyValidator.sol";
import {TecPaymaster} from "../src/paymaster/TecPaymaster.sol";
import {MockDeFiProtocol} from "../test/mocks/MockDeFiProtocol.sol";

contract DeployTecCScript is Script {
    function run() external {
        // Default to Anvil Account 0
        uint256 deployerPrivateKey =
            vm.envOr("PRIVATE_KEY", uint256(0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80));
        address deployer = vm.addr(deployerPrivateKey);
        address entryPoint = vm.envOr("ENTRYPOINT_ADDRESS", address(0x0000000071727De22E5E9d8BAf0edAc6f37da032));
        address rootOwner = vm.envOr("ROOT_OWNER", deployer);

        console.log("Deploying Tec-C Suite with deployer:", deployer);
        console.log("Root Owner (Passkey):", rootOwner);

        vm.startBroadcast(deployerPrivateKey);

        // 1. Deploy Core Security Hook (IMMUTABLE)
        TetherGuardHook hook = new TetherGuardHook();
        console.log("TetherGuardHook deployed at:", address(hook));

        // 2. Deploy Session Key Validator
        SessionKeyValidator validator = new SessionKeyValidator();
        console.log("SessionKeyValidator deployed at:", address(validator));

        // 3. Deploy Anti-Griefing Paymaster
        TecPaymaster paymaster = new TecPaymaster(entryPoint);
        console.log("TecPaymaster deployed at:", address(paymaster));

        // 4. Deploy Master TecAccount
        TecAccount account = new TecAccount(entryPoint);
        account.initialize(rootOwner, address(hook), address(validator));
        console.log("TecAccount initialized at:", address(account));

        // 5. Deploy Mock DeFi Protocols for live simulation
        MockDeFiProtocol lido = new MockDeFiProtocol();
        MockDeFiProtocol curveLP = new MockDeFiProtocol();
        console.log("Mock Lido Staking deployed at:", address(lido));
        console.log("Mock Curve LP deployed at:", address(curveLP));

        // 6. Configure Default Policies: $500 Tether Radius (0.2 ether), Tier 2 Balanced
        hook.initializeAccountPolicy(address(account), rootOwner, 0.2 ether, 2);
        hook.setTargetWhitelist(address(account), address(lido), true, 1); // Lido = Tier 1 (Conservative)
        hook.setTargetWhitelist(address(account), address(curveLP), true, 2); // Curve = Tier 2 (Balanced)

        vm.stopBroadcast();

        console.log("Tec-C Deployment and Initial Policy setup completed successfully.");
    }
}

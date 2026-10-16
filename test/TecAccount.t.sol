// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {TecAccount} from "../src/TecAccount.sol";
import {TetherGuardHook} from "../src/hooks/TetherGuardHook.sol";
import {SessionKeyValidator} from "../src/validators/SessionKeyValidator.sol";
import {MockDeFiProtocol} from "./mocks/MockDeFiProtocol.sol";
import {MODULE_TYPE_HOOK, MODULE_TYPE_VALIDATOR} from "../src/interfaces/IERC7579Account.sol";

contract TecAccountTest is Test {
    TecAccount public account;
    TetherGuardHook public hook;
    SessionKeyValidator public validator;
    MockDeFiProtocol public lidoStaking;
    MockDeFiProtocol public drainerExploit;

    address public entryPoint = address(0xEEEE);
    address public rootOwner = address(0xAA11); // Passkey WebAuthn FaceID owner
    uint256 public sessionKeyPrivKey = 0xA11CE;
    address public sessionKey;

    uint256 public constant TETHER_RADIUS = 0.5 ether; // $500 equivalent radius

    function setUp() public {
        sessionKey = vm.addr(sessionKeyPrivKey);

        // Deploy contracts
        hook = new TetherGuardHook();
        validator = new SessionKeyValidator();
        account = new TecAccount(entryPoint);
        lidoStaking = new MockDeFiProtocol();
        drainerExploit = new MockDeFiProtocol();

        // Initialize TecAccount
        account.initialize(rootOwner, address(hook), address(validator));

        // Initialize TetherGuardHook policy: 0.5 ETH radius, Balanced Tier
        hook.initializeAccountPolicy(address(account), rootOwner, TETHER_RADIUS, 2);

        // Whitelist Lido staking
        vm.prank(rootOwner);
        hook.setTargetWhitelist(address(account), address(lidoStaking), true, 2);

        // Authorize AI Session Key
        vm.prank(rootOwner);
        hook.setSessionKeyAuthorization(address(account), sessionKey, true);

        // Register session key in validator
        vm.prank(address(account));
        validator.registerSessionKey(
            address(account),
            sessionKey,
            uint48(block.timestamp),
            uint48(block.timestamp + 1 days),
            keccak256("MandateCommitment")
        );

        // Fund smart account with 100 ETH
        vm.deal(address(account), 100 ether);
    }

    function test_Initialization() public view {
        assertEq(account.accountId(), "tec-c.smart-account.v1");
        assertEq(account.rootOwner(), rootOwner);
        assertEq(address(account.installedHook()), address(hook));
        assertEq(address(account.installedValidator()), address(validator));
        assertTrue(account.isModuleInstalled(MODULE_TYPE_HOOK, address(hook), ""));
        assertTrue(account.isModuleInstalled(MODULE_TYPE_VALIDATOR, address(validator), ""));
    }

    function test_Execute_WithinTetherRadius_Success() public {
        uint256 stakeAmount = 0.2 ether;
        bytes memory callPayload = abi.encodeWithSelector(MockDeFiProtocol.stake.selector);

        // Calldata layout for TecAccount: target (20 bytes) || value (32 bytes) || data
        bytes memory executionCalldata = abi.encodePacked(address(lidoStaking), uint256(stakeAmount), callPayload);

        // Execute via Session Key through Account
        vm.prank(rootOwner);
        account.execute(bytes32(0), executionCalldata);

        // Invariants verified
        assertEq(lidoStaking.balances(address(account)), stakeAmount);
        assertEq(address(lidoStaking).balance, stakeAmount);
    }

    function test_Execute_ExceedingTetherRadius_Reverts() public {
        // AI Session Key tries to execute 0.8 ETH (> 0.5 ETH radius)
        uint256 excessiveAmount = 0.8 ether;
        bytes memory callPayload = abi.encodeWithSelector(MockDeFiProtocol.stake.selector);

        bytes memory executionCalldata = abi.encodePacked(address(lidoStaking), uint256(excessiveAmount), callPayload);

        // When executed by EntryPoint on behalf of Session Key
        vm.prank(entryPoint);
        vm.expectRevert(
            abi.encodeWithSelector(TetherGuardHook.TetherRadiusExceeded.selector, excessiveAmount, TETHER_RADIUS)
        );
        account.execute(bytes32(0), executionCalldata);

        // Verify account balance was completely protected
        assertEq(address(account).balance, 100 ether);
        assertEq(lidoStaking.balances(address(account)), 0);
    }

    function test_Execute_MaliciousTargetDrain_Reverts() public {
        // Adversarial prompt injection attacks account to send funds to unverified drainer contract
        bytes memory executionCalldata = abi.encodePacked(address(drainerExploit), uint256(0.1 ether), hex"");

        vm.prank(entryPoint);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.UnauthorizedTarget.selector, address(drainerExploit)));
        account.execute(bytes32(0), executionCalldata);

        // Account funds protected
        assertEq(address(account).balance, 100 ether);
    }

    function test_BreakingTheTether_BiometricFaceID_Success() public {
        // Passkey Root Owner initiates transaction exceeding Tether Radius (25 ETH)
        uint256 breakoutAmount = 25 ether;
        bytes memory callPayload = abi.encodeWithSelector(MockDeFiProtocol.stake.selector);

        bytes memory executionCalldata = abi.encodePacked(address(lidoStaking), uint256(breakoutAmount), callPayload);

        // 1. "Not if they are logged in 5alas!": Without active biometric verification, breakout reverts!
        vm.prank(rootOwner);
        vm.expectRevert(TetherGuardHook.BiometricVerificationRequired.selector);
        account.execute(bytes32(0), executionCalldata);

        // 2. User completes biometric verification (FaceID) -> opens 5-minute window
        vm.prank(rootOwner);
        hook.completeBiometricVerification(address(account));
        assertTrue(hook.isBiometricActive(address(account)));

        // 3. Now Root Owner executes directly during active window -> Success!
        vm.prank(rootOwner);
        account.execute(bytes32(0), executionCalldata);

        // Breakout succeeded!
        assertEq(lidoStaking.balances(address(account)), breakoutAmount);
        assertEq(address(account).balance, 100 ether - breakoutAmount);
    }

    function test_Initialization_FrontRunning_Reverts() public {
        TecAccount uninit = new TecAccount(entryPoint);
        address attacker = address(0xBAD);
        vm.prank(attacker);
        vm.expectRevert("UNAUTHORIZED_INIT");
        uninit.initialize(attacker, address(0), address(0));
    }

    function test_Execute_SelfTargetHook_Reverts() public {
        // AI Session key attempts to call setTetherRadius on TetherGuardHook via TecAccount.execute
        bytes memory callPayload = abi.encodeWithSelector(
            TetherGuardHook.setTetherRadius.selector, address(account), 1_000_000 ether, uint8(3)
        );
        bytes memory executionCalldata = abi.encodePacked(address(hook), uint256(0), callPayload);

        // EntryPoint executing on behalf of AI Session Key
        vm.prank(entryPoint);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.UnauthorizedTarget.selector, address(hook)));
        account.execute(bytes32(0), executionCalldata);
    }
}

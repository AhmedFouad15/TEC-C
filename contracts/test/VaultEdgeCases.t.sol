// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {TecAccount} from "../src/TecAccount.sol";
import {TetherGuardHook} from "../src/hooks/TetherGuardHook.sol";
import {PortfolioValuator} from "../src/hooks/PortfolioValuator.sol";
import {SessionKeyValidator} from "../src/validators/SessionKeyValidator.sol";
import {WebAuthnP256Validator} from "../src/validators/WebAuthnP256Validator.sol";
import {TecPaymaster} from "../src/paymaster/TecPaymaster.sol";
import {MockDeFiProtocol} from "./mocks/MockDeFiProtocol.sol";
import {MockERC20} from "./mocks/MockERC20.sol";
import {MockChainlinkFeed} from "./mocks/MockChainlinkFeed.sol";
import {MODULE_TYPE_HOOK, MODULE_TYPE_VALIDATOR, MODULE_TYPE_EXECUTOR} from "../src/interfaces/IERC7579Account.sol";

/**
 * @title VaultEdgeCasesTest
 * @notice Exhaustive suite testing boundary conditions, zero values, unauthorized paths,
 *         cryptographic malleability, and module lifecycle edge cases.
 */
contract VaultEdgeCasesTest is Test {
    TecAccount public account;
    TetherGuardHook public hook;
    SessionKeyValidator public sessionValidator;
    WebAuthnP256Validator public passkeyValidator;
    TecPaymaster public paymaster;
    MockDeFiProtocol public mockTarget;

    address public entryPoint = address(0xEEEE);
    address public rootOwner = address(0xAA11);
    address public sessionKey = address(0xBB22);
    address public guardian = address(0xCC33);
    address public attacker = address(0xBAD);

    function setUp() public {
        hook = new TetherGuardHook(address(new PortfolioValuator()));
        sessionValidator = new SessionKeyValidator();
        passkeyValidator = new WebAuthnP256Validator();
        paymaster = new TecPaymaster(entryPoint);
        account = new TecAccount(entryPoint);
        mockTarget = new MockDeFiProtocol();

        account.initialize(rootOwner, address(hook), address(sessionValidator));

        hook.initializeAccountPolicy(address(account), rootOwner, 1.0 ether, hook.RISK_TIER_GROWTH_DEFI());

        vm.startPrank(rootOwner);
        hook.setTargetWhitelist(address(account), address(mockTarget), true, hook.RISK_TIER_GROWTH_DEFI());
        hook.setSessionKeyAuthorization(address(account), sessionKey, true);
        hook.configureDeadmanSwitch(address(account), guardian, 30 days);
        vm.stopPrank();

        vm.deal(address(account), 100 ether);
    }

    // =========================================================================
    // Edge Cases: Module Lifecycle & Access Control
    // =========================================================================

    function test_EdgeCase_ModuleInstallation_InvalidModuleType_Reverts() public {
        vm.prank(rootOwner);
        vm.expectRevert(TecAccount.InvalidModuleType.selector);
        account.installModule(999, address(0x123), hex"");
    }

    function test_EdgeCase_ModuleInstallation_OnlyRootOwner_Reverts() public {
        vm.prank(attacker);
        vm.expectRevert(TecAccount.OnlyRootOwner.selector);
        account.installModule(MODULE_TYPE_HOOK, address(0x123), hex"");
    }

    function test_EdgeCase_ModuleUninstallation_Mismatch_Reverts() public {
        vm.prank(rootOwner);
        vm.expectRevert("MISMATCH");
        account.uninstallModule(MODULE_TYPE_HOOK, address(0x9999), hex"");
    }

    function test_EdgeCase_ModuleUninstallation_InvalidType_Reverts() public {
        vm.prank(rootOwner);
        vm.expectRevert(TecAccount.InvalidModuleType.selector);
        account.uninstallModule(888, address(0x123), hex"");
    }

    function test_EdgeCase_ModuleUninstallation_And_Reinstallation_Success() public {
        vm.startPrank(rootOwner);
        // Uninstall validator
        account.uninstallModule(MODULE_TYPE_VALIDATOR, address(sessionValidator), hex"");
        assertFalse(account.isModuleInstalled(MODULE_TYPE_VALIDATOR, address(sessionValidator), hex""));

        // Reinstall WebAuthn passkey validator
        account.installModule(MODULE_TYPE_VALIDATOR, address(passkeyValidator), hex"");
        assertTrue(account.isModuleInstalled(MODULE_TYPE_VALIDATOR, address(passkeyValidator), hex""));
        vm.stopPrank();
    }

    // =========================================================================
    // Edge Cases: Account Native ETH Receiving & Zero-Value Calls
    // =========================================================================

    function test_EdgeCase_DirectETHReceive_AcceptsDeposit() public {
        uint256 balBefore = address(account).balance;
        (bool ok,) = address(account).call{value: 5 ether}("");
        assertTrue(ok);
        assertEq(address(account).balance, balBefore + 5 ether);
    }

    function test_EdgeCase_ZeroValue_EmptyCalldata_Succeeds() public {
        bytes memory execCalldata = abi.encodePacked(address(mockTarget), uint256(0), hex"");
        vm.prank(entryPoint);
        account.execute(bytes32(0), execCalldata);
    }

    function test_EdgeCase_NativeETH_ZeroDataTransfer_Success() public {
        address recipient = address(0x7777);
        bytes memory execCalldata = abi.encodePacked(recipient, uint256(0.1 ether), hex"");

        vm.startPrank(rootOwner);
        hook.setTargetWhitelist(address(account), recipient, true, hook.RISK_TIER_CORE_PRESERVATION());
        vm.stopPrank();

        vm.prank(entryPoint);
        account.execute(bytes32(0), execCalldata);
        assertEq(recipient.balance, 0.1 ether);
    }

    // =========================================================================
    // Edge Cases: Morning Review Boundary Conditions
    // =========================================================================

    function test_EdgeCase_Review_NonExistentRecord_Reverts() public {
        vm.prank(rootOwner);
        vm.expectRevert(TetherGuardHook.InvalidRecordId.selector);
        hook.ratifyTransaction(address(account), 9999);
    }

    function test_EdgeCase_Review_UnauthorizedUser_Reverts() public {
        vm.prank(attacker);
        vm.expectRevert(TetherGuardHook.UnauthorizedCaller.selector);
        hook.ratifyTransaction(address(account), 1);
    }

    // =========================================================================
    // Edge Cases: Biometrics & Sign Approval
    // =========================================================================

    function test_EdgeCase_BiometricGrace_Revocation_ImmediatelyHaltsBreakout() public {
        // User verifies biometrics -> 5m window opens
        vm.prank(rootOwner);
        hook.completeBiometricVerification(address(account));
        assertTrue(hook.isBiometricActive(address(account)));

        // User locks app / revokes verification window
        vm.prank(rootOwner);
        hook.revokeBiometricVerification(address(account));
        assertFalse(hook.isBiometricActive(address(account)));

        // Subsequent breakout attempt reverts immediately
        bytes memory breakout = abi.encodePacked(address(mockTarget), uint256(10 ether), hex"");
        vm.prank(rootOwner);
        vm.expectRevert(TetherGuardHook.BiometricVerificationRequired.selector);
        account.execute(bytes32(0), breakout);
    }

    function test_EdgeCase_SignApproval_ExplicitReject_PreventsExecution() public {
        vm.prank(rootOwner);
        hook.completeBiometricVerification(address(account));

        bytes memory breakout = abi.encodePacked(address(mockTarget), uint256(5 ether), hex"");
        bytes32 execHash = keccak256(breakout);

        // User explicitly REJECTS this execution
        vm.prank(rootOwner);
        hook.submitSignApproval(address(account), execHash, false);

        (bool approved, bool rejected) = hook.getSignApprovalStatus(address(account), execHash);
        assertFalse(approved);
        assertTrue(rejected);

        // AI session key attempts execution -> Reverts with ExecutionRejectedByUser!
        vm.prank(entryPoint);
        vm.expectRevert(TetherGuardHook.ExecutionRejectedByUser.selector);
        account.execute(bytes32(0), breakout);
    }

    // =========================================================================
    // Edge Cases: Dead-Man's Switch Boundaries
    // =========================================================================

    function test_EdgeCase_DeadmanSwitch_ZeroGuardian_Reverts() public {
        vm.prank(rootOwner);
        vm.expectRevert("INVALID_GUARDIAN");
        hook.configureDeadmanSwitch(address(account), address(0), 30 days);
    }

    function test_EdgeCase_DeadmanSwitch_ExactBoundaryTrigger() public {
        // Fast-forward to 1 second before timeout expires
        vm.warp(block.timestamp + 30 days - 1);

        // Still not eligible before boundary
        assertFalse(hook.isDeadmanSwitchTriggerable(address(account)));
        vm.prank(guardian);
        vm.expectRevert();
        hook.triggerDeadmanRecovery(address(account), address(0x8888));

        // 1 second later: reached exact timeout, eligible!
        vm.warp(block.timestamp + 1);
        assertTrue(hook.isDeadmanSwitchTriggerable(address(account)));
        vm.prank(guardian);
        hook.triggerDeadmanRecovery(address(account), address(0x8888));

        TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(address(account));
        assertEq(p.rootOwner, address(0x8888));
    }

    function test_EdgeCase_CustomHeartbeatTimeout_Below1Hour_Reverts() public {
        vm.prank(rootOwner);
        vm.expectRevert("TIMEOUT_TOO_SHORT");
        hook.configureAIHeartbeatTimeout(address(account), 30 minutes);
    }

    // =========================================================================
    // Edge Cases: SessionKeyValidator Registration Boundaries
    // =========================================================================

    function test_EdgeCase_SessionKey_ZeroAddress_Reverts() public {
        vm.prank(address(account));
        vm.expectRevert(SessionKeyValidator.InvalidSignature.selector);
        sessionValidator.registerSessionKey(
            address(account), address(0), uint48(block.timestamp), uint48(block.timestamp + 1 days), bytes32(0)
        );
    }

    function test_EdgeCase_SessionKey_InvalidTimeRange_Reverts() public {
        vm.prank(address(account));
        vm.expectRevert(SessionKeyValidator.InvalidTimeRange.selector);
        sessionValidator.registerSessionKey(
            address(account),
            sessionKey,
            uint48(block.timestamp + 2 days), // validAfter > validUntil!
            uint48(block.timestamp + 1 days),
            bytes32(0)
        );
    }

    // =========================================================================
    // Edge Cases: TecPaymaster Withdrawal Boundaries
    // =========================================================================

    function test_EdgeCase_Paymaster_WithdrawZeroBalance_Reverts() public {
        address emptyUser = address(0x9999);
        vm.prank(emptyUser);
        vm.expectRevert(TecPaymaster.InsufficientAccountBalance.selector);
        paymaster.withdrawForAccount(payable(emptyUser), 1 ether);
    }

    function test_EdgeCase_Paymaster_OwnerWithdrawal_Unauthorized_Reverts() public {
        vm.prank(attacker);
        vm.expectRevert(TecPaymaster.OnlyOwner.selector);
        paymaster.withdraw(payable(attacker), 1 ether);
    }
}

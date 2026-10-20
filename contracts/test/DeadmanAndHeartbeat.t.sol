// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {TetherGuardHook} from "../src/hooks/TetherGuardHook.sol";
import {PortfolioValuator} from "../src/hooks/PortfolioValuator.sol";
import {MockDeFiProtocol} from "./mocks/MockDeFiProtocol.sol";

contract DeadmanAndHeartbeatTest is Test {
    TetherGuardHook public hook;
    MockDeFiProtocol public lidoStaking;

    address public rootOwner = address(0xAA11);
    address public tecAccount = address(0xBB22);
    address public sessionKey = address(0xCC33);
    address public corporateGuardian = address(0xDD44);
    address public successorOwner = address(0xEE55);

    uint256 public constant TETHER_RADIUS = 0.5 ether;
    uint8 public constant TIER_BALANCED = 2;

    function setUp() public {
        hook = new TetherGuardHook(address(new PortfolioValuator()));
        lidoStaking = new MockDeFiProtocol();

        hook.initializeAccountPolicy(tecAccount, rootOwner, TETHER_RADIUS, TIER_BALANCED);

        vm.prank(rootOwner);
        hook.setTargetWhitelist(tecAccount, address(lidoStaking), true, TIER_BALANCED);

        vm.prank(rootOwner);
        hook.setSessionKeyAuthorization(tecAccount, sessionKey, true);

        vm.deal(tecAccount, 100 ether);
    }

    // =========================================================================
    // --- Inactive AI Heartbeat Tests ---
    // =========================================================================

    function test_AIHeartbeat_InitialStatus_Alive() public view {
        // When freshly deployed, AI Heartbeat is alive
        assertTrue(hook.isAIHeartbeatAlive(tecAccount));
    }

    function test_AIHeartbeat_Record_Success() public {
        // Session key broadcasts liveness heartbeat
        vm.prank(sessionKey);
        hook.recordAIHeartbeat(tecAccount);

        assertEq(hook.lastAIHeartbeat(tecAccount), block.timestamp);
        assertTrue(hook.isAIHeartbeatAlive(tecAccount));
    }

    function test_AIHeartbeat_StaleTimeout_RevertsAutonomousExecution() public {
        // AI records heartbeat at t = 0
        vm.prank(sessionKey);
        hook.recordAIHeartbeat(tecAccount);

        uint256 beatTime = hook.lastAIHeartbeat(tecAccount);

        // 49 hours elapse without an AI heartbeat (> 48h timeout!)
        vm.warp(block.timestamp + 49 hours);
        assertFalse(hook.isAIHeartbeatAlive(tecAccount));

        // AI attempts autonomous transaction -> Reverts with AIHeartbeatStale!
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.1 ether), hex"");
        vm.prank(tecAccount);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.AIHeartbeatStale.selector, beatTime, block.timestamp));
        hook.preCheck(sessionKey, 0.1 ether, msgData);
    }

    function test_AIHeartbeat_SuccessfulExecution_RefreshesHeartbeat() public {
        // AI executes normal transaction within limit
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.1 ether), hex"");

        vm.prank(tecAccount);
        hook.preCheck(sessionKey, 0.1 ether, msgData);

        // Heartbeat was automatically updated to current block timestamp!
        assertEq(hook.lastAIHeartbeat(tecAccount), block.timestamp);
        assertTrue(hook.isAIHeartbeatAlive(tecAccount));
    }

    function test_AIHeartbeat_CustomTimeout_Enforced() public {
        // Root owner configures strict 2-hour heartbeat timeout
        vm.prank(rootOwner);
        hook.configureAIHeartbeatTimeout(tecAccount, 2 hours);

        vm.prank(sessionKey);
        hook.recordAIHeartbeat(tecAccount);

        // Warp 2 hours and 1 minute
        vm.warp(block.timestamp + 2 hours + 1 minutes);
        assertFalse(hook.isAIHeartbeatAlive(tecAccount));

        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.1 ether), hex"");
        vm.prank(tecAccount);
        vm.expectRevert();
        hook.preCheck(sessionKey, 0.1 ether, msgData);
    }

    // =========================================================================
    // --- Dead-Man's Switch Tests ---
    // =========================================================================

    function test_DeadmanSwitch_Configure_Success() public {
        // Root owner configures corporate guardian with default 90-day timeout
        vm.prank(rootOwner);
        hook.configureDeadmanSwitch(tecAccount, corporateGuardian, 90 days);

        assertEq(hook.deadmanGuardians(tecAccount), corporateGuardian);
        assertEq(hook.deadmanTimeouts(tecAccount), 90 days);
        assertFalse(hook.isDeadmanSwitchTriggerable(tecAccount));
    }

    function test_DeadmanSwitch_PrematureTrigger_Reverts() public {
        vm.prank(rootOwner);
        hook.configureDeadmanSwitch(tecAccount, corporateGuardian, 90 days);

        // Only 30 days elapse
        vm.warp(block.timestamp + 30 days);

        // Guardian attempts recovery prematurely -> Reverts!
        vm.prank(corporateGuardian);
        vm.expectRevert();
        hook.triggerDeadmanRecovery(tecAccount, successorOwner);
    }

    function test_DeadmanSwitch_ElapsedTimeout_Success() public {
        vm.prank(rootOwner);
        hook.configureDeadmanSwitch(tecAccount, corporateGuardian, 90 days);

        // 91 days of total user inactivity elapse (> 90 days)
        vm.warp(block.timestamp + 91 days);
        assertTrue(hook.isDeadmanSwitchTriggerable(tecAccount));

        // Guardian triggers recovery -> Rotates rootOwner to corporate successor!
        vm.prank(corporateGuardian);
        hook.triggerDeadmanRecovery(tecAccount, successorOwner);

        TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(tecAccount);
        assertEq(p.rootOwner, successorOwner);
    }

    function test_DeadmanSwitch_UserActivityPings_ResetsTimer() public {
        vm.prank(rootOwner);
        hook.configureDeadmanSwitch(tecAccount, corporateGuardian, 90 days);

        // 80 days pass
        vm.warp(block.timestamp + 80 days);

        // User interacts with vault (e.g. completes FaceID biometric verification or pings activity)
        vm.prank(rootOwner);
        hook.pingUserActivity(tecAccount);

        // Warp another 30 days (total 110 days since beginning, but only 30 days since last activity!)
        vm.warp(block.timestamp + 30 days);
        assertFalse(hook.isDeadmanSwitchTriggerable(tecAccount));

        // Recovery attempt reverts because user was active within last 90 days!
        vm.prank(corporateGuardian);
        vm.expectRevert();
        hook.triggerDeadmanRecovery(tecAccount, successorOwner);
    }

    function test_DeadmanSwitch_UnauthorizedCaller_Reverts() public {
        vm.prank(rootOwner);
        hook.configureDeadmanSwitch(tecAccount, corporateGuardian, 90 days);

        vm.warp(block.timestamp + 95 days);

        // Random attacker tries to call triggerDeadmanRecovery -> Reverts!
        vm.prank(address(0xDEAD));
        vm.expectRevert(TetherGuardHook.UnauthorizedGuardian.selector);
        hook.triggerDeadmanRecovery(tecAccount, successorOwner);
    }
}

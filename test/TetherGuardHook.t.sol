// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import { Test, console } from "forge-std/Test.sol";
import { TetherGuardHook } from "../src/hooks/TetherGuardHook.sol";
import { MockDeFiProtocol } from "./mocks/MockDeFiProtocol.sol";

contract TetherGuardHookTest is Test {
    TetherGuardHook public hook;
    MockDeFiProtocol public lidoStaking;
    MockDeFiProtocol public maliciousDrainer;

    address public rootOwner = address(0xAA11);      // Passkey WebAuthn FaceID owner
    address public tecAccount = address(0xBB22);     // Tec-C Smart Account
    address public sessionKey = address(0xCC33);     // AI Agent ephemeral session key

    uint256 public constant TETHER_RADIUS = 0.5 ether; // $500 equivalent radius

    uint8 public constant TIER_CORE_PRESERVATION = 1; // Giga tokens, Stablecoins, Commodities, Shibor MMFs
    uint8 public constant TIER_GROWTH_DEFI       = 2; // Liquid Staking stETH, AMMs, Curve/Uniswap LPs
    uint8 public constant TIER_UNRESTRICTED      = 3; // Omni-Universe (allows everything)

    uint8 public constant TIER_CONSERVATIVE = 1;
    uint8 public constant TIER_BALANCED     = 2;
    uint8 public constant TIER_AGGRESSIVE   = 3;

    function setUp() public {
        hook = new TetherGuardHook();
        lidoStaking = new MockDeFiProtocol();
        maliciousDrainer = new MockDeFiProtocol();

        // Initialize account policy: Tether Radius = 0.5 ETH, Tier 2 (Balanced)
        hook.initializeAccountPolicy(tecAccount, rootOwner, TETHER_RADIUS, TIER_BALANCED);

        // Whitelist Lido staking as Tier 2 (Balanced)
        vm.prank(rootOwner);
        hook.setTargetWhitelist(tecAccount, address(lidoStaking), true, TIER_BALANCED);

        // Authorize AI Session Key
        vm.prank(rootOwner);
        hook.setSessionKeyAuthorization(tecAccount, sessionKey, true);

        // Fund tecAccount
        vm.deal(tecAccount, 100 ether);
    }

    function test_Initialization() public view {
        (
            uint256 radius,
            uint256 dailySpent,
            uint256 epoch,
            uint8 riskTier,
            bool emergencyPaused,
            address owner
        ) = hook.policies(tecAccount);

        assertEq(radius, TETHER_RADIUS);
        assertEq(dailySpent, 0);
        assertEq(riskTier, TIER_BALANCED);
        assertFalse(emergencyPaused);
        assertEq(owner, rootOwner);
        assertEq(epoch, block.timestamp / 1 days);
    }

    function test_ExecutionWithinTetherRadius_Succeeds() public {
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.2 ether), hex"");

        vm.prank(tecAccount);
        bytes memory hookData = hook.preCheck(sessionKey, 0.2 ether, msgData);

        // Verify daily spent increased
        (, uint256 dailySpent, , , , ) = hook.policies(tecAccount);
        assertEq(dailySpent, 0.2 ether);
        assertEq(hook.getRemainingRadius(tecAccount), 0.3 ether);

        // Execute postCheck
        vm.prank(tecAccount);
        hook.postCheck(hookData);
        assertEq(hook.totalAuditedExecutions(), 1);
    }

    function test_ExecutionExceedingTetherRadius_Reverts() public {
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.6 ether), hex"");

        // Attempting to spend 0.6 ETH when radius is 0.5 ETH must revert
        vm.prank(tecAccount);
        vm.expectRevert(
            abi.encodeWithSelector(
                TetherGuardHook.TetherRadiusExceeded.selector,
                0.6 ether,
                0.5 ether
            )
        );
        hook.preCheck(sessionKey, 0.6 ether, msgData);
    }

    function test_CumulativeSpending_ExceedingRadius_Reverts() public {
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.3 ether), hex"");

        // First tx: 0.3 ETH -> OK
        vm.prank(tecAccount);
        hook.preCheck(sessionKey, 0.3 ether, msgData);

        // Second tx: 0.3 ETH -> 0.3 + 0.3 = 0.6 > 0.5 -> Reverts!
        vm.prank(tecAccount);
        vm.expectRevert(
            abi.encodeWithSelector(
                TetherGuardHook.TetherRadiusExceeded.selector,
                0.3 ether,
                0.2 ether // only 0.2 remaining
            )
        );
        hook.preCheck(sessionKey, 0.3 ether, msgData);
    }

    function test_EpochReset_ReplenishesTetherRadius() public {
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.4 ether), hex"");

        // Day 1: Spend 0.4 ETH
        vm.prank(tecAccount);
        hook.preCheck(sessionKey, 0.4 ether, msgData);
        assertEq(hook.getRemainingRadius(tecAccount), 0.1 ether);

        // Fast forward 24 hours (1 epoch)
        vm.warp(block.timestamp + 1 days + 1);

        // Radius is replenished! Can spend 0.4 ETH again
        assertEq(hook.getRemainingRadius(tecAccount), TETHER_RADIUS);

        vm.prank(tecAccount);
        hook.preCheck(sessionKey, 0.4 ether, msgData);
        assertEq(hook.getRemainingRadius(tecAccount), 0.1 ether);
    }

    function test_UnauthorizedTarget_Reverts() public {
        // Attempting to call maliciousDrainer which is NOT whitelisted
        bytes memory msgData = abi.encodePacked(address(maliciousDrainer), uint256(0.1 ether), hex"");

        vm.prank(tecAccount);
        vm.expectRevert(
            abi.encodeWithSelector(
                TetherGuardHook.UnauthorizedTarget.selector,
                address(maliciousDrainer)
            )
        );
        hook.preCheck(sessionKey, 0.1 ether, msgData);
    }

    function test_AssetTierNotPermitted_Reverts() public {
        // Whitelist high-risk asset as Tier 3 (Aggressive)
        MockDeFiProtocol memeCoinLP = new MockDeFiProtocol();
        vm.prank(rootOwner);
        hook.setTargetWhitelist(tecAccount, address(memeCoinLP), true, TIER_AGGRESSIVE);

        // Account is configured as Tier 2 (Balanced). Attempting Tier 3 reverts!
        bytes memory msgData = abi.encodePacked(address(memeCoinLP), uint256(0.1 ether), hex"");

        vm.prank(tecAccount);
        vm.expectRevert(
            abi.encodeWithSelector(
                TetherGuardHook.AssetTierNotPermitted.selector,
                address(memeCoinLP),
                TIER_AGGRESSIVE,
                TIER_BALANCED
            )
        );
        hook.preCheck(sessionKey, 0.1 ether, msgData);
    }

    function test_BreakingTheTether_BiometricFaceID_BypassesLimit() public {
        // Root Owner initiates a transaction exceeding the radius (e.g. 10 ETH!)
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(10 ether), hex"");

        vm.prank(tecAccount);
        bytes memory hookData = hook.preCheck(rootOwner, 10 ether, msgData);

        (bool isRoot, , uint256 value, ) = abi.decode(hookData, (bool, address, uint256, address));
        assertTrue(isRoot);
        assertEq(value, 10 ether);

        // Daily spent for AI remains unconsumed!
        assertEq(hook.getRemainingRadius(tecAccount), TETHER_RADIUS);
    }

    function test_PegGuardCircuitBreaker_EmergencyVeto() public {
        // FinBERT NLP Sentinel detects 90% negative news (exploit detected)
        vm.prank(rootOwner);
        hook.triggerEmergencyCircuitBreaker(tecAccount, "FinBERT Veto: Protocol exploit reported on Caixin");

        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.1 ether), hex"");

        // AI Agent attempts transaction -> Halts immediately!
        vm.prank(tecAccount);
        vm.expectRevert(TetherGuardHook.EmergencyCircuitBreakerActive.selector);
        hook.preCheck(sessionKey, 0.1 ether, msgData);

        // Reset circuit breaker
        vm.prank(rootOwner);
        hook.resetEmergencyCircuitBreaker(tecAccount);

        // Now transaction succeeds
        vm.prank(tecAccount);
        hook.preCheck(sessionKey, 0.1 ether, msgData);
    }

    function test_Tier1_CorePreservation_RevertsOnTier2Growth() public {
        // Set account to Tier 1: Core Preservation (Giga tokens, Stablecoins, Commodities, Shibor)
        vm.prank(rootOwner);
        hook.setTetherRadius(tecAccount, TETHER_RADIUS, TIER_CORE_PRESERVATION);

        // Attempting to call Lido Staking (Tier 2 Growth/DeFi) must revert!
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.1 ether), hex"");

        vm.prank(tecAccount);
        vm.expectRevert(
            abi.encodeWithSelector(
                TetherGuardHook.AssetTierNotPermitted.selector,
                address(lidoStaking),
                TIER_GROWTH_DEFI,
                TIER_CORE_PRESERVATION
            )
        );
        hook.preCheck(sessionKey, 0.1 ether, msgData);
    }

    function test_Tier3_Unrestricted_AllowsAnyAssetAndProtocol() public {
        // Set account to Tier 3: Omni-Universe / Unrestricted (Allows everything to be held)
        vm.prank(rootOwner);
        hook.setTetherRadius(tecAccount, TETHER_RADIUS, TIER_UNRESTRICTED);

        // Call an unwhitelisted contract (e.g. maliciousDrainer or any random protocol)
        bytes memory msgData = abi.encodePacked(address(maliciousDrainer), uint256(0.2 ether), hex"");

        // In Tier 3, target whitelist and tier veto are bypassed! Operation succeeds within radius.
        vm.prank(tecAccount);
        bytes memory hookData = hook.preCheck(sessionKey, 0.2 ether, msgData);

        // Daily spent tracked accurately
        assertEq(hook.getRemainingRadius(tecAccount), 0.3 ether);

        vm.prank(tecAccount);
        hook.postCheck(hookData);
    }

    function test_Tier3_Unrestricted_StillEnforcesTetherRadius() public {
        // In Tier 3 Unrestricted, the AI can hold anything, but physically CANNOT exceed the Tether Radius!
        vm.prank(rootOwner);
        hook.setTetherRadius(tecAccount, TETHER_RADIUS, TIER_UNRESTRICTED);

        bytes memory msgData = abi.encodePacked(address(maliciousDrainer), uint256(0.8 ether), hex"");

        // Attempting 0.8 ETH > 0.5 ETH radius still reverts!
        vm.prank(tecAccount);
        vm.expectRevert(
            abi.encodeWithSelector(
                TetherGuardHook.TetherRadiusExceeded.selector,
                0.8 ether,
                0.5 ether
            )
        );
        hook.preCheck(sessionKey, 0.8 ether, msgData);
    }

    function test_Tier3_Unrestricted_StillEnforcesPegGuardCircuitBreaker() public {
        // Even in Tier 3 Unrestricted, PegGuard NLP Sentinel can halt all execution
        vm.prank(rootOwner);
        hook.setTetherRadius(tecAccount, TETHER_RADIUS, TIER_UNRESTRICTED);

        vm.prank(rootOwner);
        hook.triggerEmergencyCircuitBreaker(tecAccount, "FinBERT Veto: Market crash or protocol hack");

        bytes memory msgData = abi.encodePacked(address(maliciousDrainer), uint256(0.1 ether), hex"");

        vm.prank(tecAccount);
        vm.expectRevert(TetherGuardHook.EmergencyCircuitBreakerActive.selector);
        hook.preCheck(sessionKey, 0.1 ether, msgData);
    }
}


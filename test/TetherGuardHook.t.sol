// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import { Test, console } from "forge-std/Test.sol";
import { TetherGuardHook } from "../src/hooks/TetherGuardHook.sol";
import { MockDeFiProtocol } from "./mocks/MockDeFiProtocol.sol";

contract TetherGuardHookTest is Test {
    TetherGuardHook public hook;
    MockDeFiProtocol public lidoStaking;
    MockDeFiProtocol public maliciousDrainer;

    uint256 public rootOwnerPk = 0xA11CE;
    address public rootOwner;
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
        rootOwner = vm.addr(rootOwnerPk);
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
        TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(tecAccount);

        assertEq(p.tetherRadius, TETHER_RADIUS);
        assertEq(p.dailySpent, 0);
        assertEq(p.riskTier, TIER_BALANCED);
        assertEq(p.rootOwner, rootOwner);
        assertEq(p.currentEpoch, block.timestamp / 1 days);
        assertFalse(p.isDynamicElasticityEnabled); // default static mode
    }

    function test_ExecutionWithinTetherRadius_Succeeds() public {
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.2 ether), hex"");

        vm.prank(tecAccount);
        bytes memory hookData = hook.preCheck(sessionKey, 0.2 ether, msgData);

        // Verify daily spent increased
        TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(tecAccount);
        assertEq(p.dailySpent, 0.2 ether);
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

    function test_BreakingTheTether_WithoutBiometric_Reverts() public {
        // Root Owner initiates a transaction exceeding the radius (e.g. 10 ETH) WITHOUT active biometric verification
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(10 ether), hex"");

        // "Not if they are logged in 5alas!" -> Must revert with BiometricVerificationRequired!
        vm.prank(tecAccount);
        vm.expectRevert(TetherGuardHook.BiometricVerificationRequired.selector);
        hook.preCheck(rootOwner, 10 ether, msgData);
    }

    function test_BreakingTheTether_BiometricFaceID_BypassesLimit() public {
        // User completes biometric verification (FaceID) -> opens 5-minute active window
        vm.prank(rootOwner);
        hook.completeBiometricVerification(tecAccount);
        assertTrue(hook.isBiometricActive(tecAccount));

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

    function test_BreakingTheTether_BiometricWindowExpires_Reverts() public {
        // User completes biometric verification
        vm.prank(rootOwner);
        hook.completeBiometricVerification(tecAccount);

        // Warp 5 minutes and 1 second into future -> window expires
        vm.warp(block.timestamp + 301);
        assertFalse(hook.isBiometricActive(tecAccount));

        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(10 ether), hex"");
        vm.prank(tecAccount);
        vm.expectRevert(TetherGuardHook.BiometricVerificationRequired.selector);
        hook.preCheck(rootOwner, 10 ether, msgData);
    }

    function test_BreakingTheTether_BrainInitiated_SignApproval_Accept() public {
        // User completes biometric verification -> 5m window is active
        vm.prank(rootOwner);
        hook.completeBiometricVerification(tecAccount);

        // Brain prepares 10 ETH breakout call to Lido
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(10 ether), hex"");
        bytes32 execHash = keccak256(msgData);

        // Brain asks user for sign approval; user clicks [Accept] -> simple signature approval (no biometric prompt!)
        vm.prank(rootOwner);
        hook.submitSignApproval(tecAccount, execHash, true);

        (bool isApproved, bool isRejected) = hook.getSignApprovalStatus(tecAccount, execHash);
        assertTrue(isApproved);
        assertFalse(isRejected);

        // Brain executes with user's sign approval during 5m window
        vm.prank(tecAccount);
        bytes memory hookData = hook.preCheck(sessionKey, 10 ether, msgData);

        (bool isRoot, , uint256 value, ) = abi.decode(hookData, (bool, address, uint256, address));
        assertTrue(isRoot);
        assertEq(value, 10 ether);
    }

    function test_BreakingTheTether_BrainInitiated_SignApproval_Reject() public {
        // User completes biometric verification
        vm.prank(rootOwner);
        hook.completeBiometricVerification(tecAccount);

        // Brain prepares 10 ETH breakout call
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(10 ether), hex"");
        bytes32 execHash = keccak256(msgData);

        // User clicks [Reject]!
        vm.prank(rootOwner);
        hook.submitSignApproval(tecAccount, execHash, false);

        (bool isApproved, bool isRejected) = hook.getSignApprovalStatus(tecAccount, execHash);
        assertFalse(isApproved);
        assertTrue(isRejected);

        // Brain attempts to execute -> Reverts with ExecutionRejectedByUser!
        vm.prank(tecAccount);
        vm.expectRevert(TetherGuardHook.ExecutionRejectedByUser.selector);
        hook.preCheck(sessionKey, 10 ether, msgData);
    }

    function test_BreakingTheTether_BrainInitiated_GaslessSignatureApproval() public {
        // User completes biometric verification -> 5m window is active
        vm.prank(rootOwner);
        hook.completeBiometricVerification(tecAccount);

        // Brain prepares 10 ETH breakout call to Lido
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(10 ether), hex"");
        bytes32 execHash = keccak256(msgData);

        // User generates off-chain signature approving this execution (Accept = true)
        uint256 deadline = block.timestamp + 10 minutes;
        {
            bytes32 messageHash = keccak256(abi.encode(tecAccount, execHash, true, hook.signApprovalNonces(tecAccount), deadline, block.chainid));
            bytes32 ethSignedMessageHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(rootOwnerPk, ethSignedMessageHash);
            hook.submitSignApprovalWithSignature(tecAccount, execHash, true, deadline, abi.encodePacked(r, s, v));
        }

        (bool isApproved, bool isRejected) = hook.getSignApprovalStatus(tecAccount, execHash);
        assertTrue(isApproved);
        assertFalse(isRejected);

        // Brain executes successfully
        vm.prank(tecAccount);
        bytes memory hookData = hook.preCheck(sessionKey, 10 ether, msgData);

        (bool isRoot, , uint256 value, ) = abi.decode(hookData, (bool, address, uint256, address));
        assertTrue(isRoot);
        assertEq(value, 10 ether);
    }

    function test_submitSignApprovalWithSignature_ExpiredDeadline_Reverts() public {
        vm.prank(rootOwner);
        hook.completeBiometricVerification(tecAccount);

        bytes32 execHash = keccak256(abi.encodePacked(address(lidoStaking), uint256(10 ether), hex""));
        uint256 deadline = block.timestamp + 2 minutes;
        bytes memory signature;
        {
            bytes32 messageHash = keccak256(abi.encode(tecAccount, execHash, true, hook.signApprovalNonces(tecAccount), deadline, block.chainid));
            bytes32 ethSignedMessageHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(rootOwnerPk, ethSignedMessageHash);
            signature = abi.encodePacked(r, s, v);
        }

        // Warp time past signature deadline (3m), while 5m biometric window remains active
        vm.warp(block.timestamp + 3 minutes);

        vm.expectRevert(TetherGuardHook.ExpiredSignature.selector);
        hook.submitSignApprovalWithSignature(tecAccount, execHash, true, deadline, signature);
    }

    function test_submitSignApprovalWithSignature_ReplayAttack_Reverts() public {
        vm.prank(rootOwner);
        hook.completeBiometricVerification(tecAccount);

        bytes32 execHash = keccak256(abi.encodePacked(address(lidoStaking), uint256(10 ether), hex""));
        uint256 deadline = block.timestamp + 10 minutes;
        bytes memory signature;
        {
            bytes32 messageHash = keccak256(abi.encode(tecAccount, execHash, true, hook.signApprovalNonces(tecAccount), deadline, block.chainid));
            bytes32 ethSignedMessageHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
            (uint8 v, bytes32 r, bytes32 s) = vm.sign(rootOwnerPk, ethSignedMessageHash);
            signature = abi.encodePacked(r, s, v);
        }

        // First submission succeeds
        hook.submitSignApprovalWithSignature(tecAccount, execHash, true, deadline, signature);

        // Attacker attempts to replay the exact same signature -> reverts because nonce incremented!
        vm.expectRevert(TetherGuardHook.InvalidApprovalSignature.selector);
        hook.submitSignApprovalWithSignature(tecAccount, execHash, true, deadline, signature);
    }

    function test_initializeAccountPolicy_FrontRunning_Reverts() public {
        address uninitAccount = address(0x4444);
        address attacker = address(0x6666);

        vm.prank(attacker);
        vm.expectRevert("UNAUTHORIZED_INIT");
        hook.initializeAccountPolicy(uninitAccount, attacker, 1 ether, TIER_BALANCED);
    }

    function test_setGlobalPriceFeed_Unauthorized_Reverts() public {
        address attacker = address(0x6666);
        vm.prank(attacker);
        vm.expectRevert(TetherGuardHook.UnauthorizedCaller.selector);
        hook.setGlobalPriceFeed(address(0x1234), address(0x5678));
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

    // --- Axis 2 Dynamic Elasticity & Adaptive Learning Tests ---

    function test_DynamicElasticity_StaticMode_Reverts() public {
        // By default, account is in static mode (user answered 'keep it limited')
        // AI attempt to autonomously adjust radius MUST revert!
        vm.prank(sessionKey);
        vm.expectRevert(TetherGuardHook.DynamicAdjustmentDisabled.selector);
        hook.autonomousRadiusAdjustment(tecAccount, 1.0 ether, "Attempted unauthorized autonomous expansion");
    }

    function test_DynamicElasticity_OptIn_StepUp_Succeeds() public {
        // User opts in during onboarding: 2 ETH initial radius, 10 ETH max ceiling
        address dynamicAccount = address(0xDD44);
        hook.initializeAccountPolicy(
            dynamicAccount,
            rootOwner,
            2.0 ether,
            TIER_GROWTH_DEFI,
            true, // enable elasticity!
            10.0 ether // max ceiling
        );

        vm.prank(rootOwner);
        hook.setSessionKeyAuthorization(dynamicAccount, sessionKey, true);

        // Fast forward 1 day so cooldown is ready
        vm.warp(block.timestamp + 1 days + 1);

        // Max 10% daily increase: 2.0 ETH -> 2.2 ETH
        vm.prank(sessionKey);
        hook.autonomousRadiusAdjustment(
            dynamicAccount,
            2.2 ether,
            "10% max daily increase after positive performance review"
        );

        TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(dynamicAccount);
        assertEq(p.tetherRadius, 2.2 ether);
    }

    function test_DynamicElasticity_ExcessiveStepUp_Reverts() public {
        // User opts in with 2 ETH radius, 10 ETH ceiling
        address dynamicAccount = address(0xDD44);
        hook.initializeAccountPolicy(
            dynamicAccount,
            rootOwner,
            2.0 ether,
            TIER_GROWTH_DEFI,
            true,
            10.0 ether
        );

        vm.prank(rootOwner);
        hook.setSessionKeyAuthorization(dynamicAccount, sessionKey, true);

        vm.warp(block.timestamp + 1 days + 1);

        // AI tries to jump from 2 ETH directly to 2.5 ETH (> 10% = 2.2 ETH max)
        vm.prank(sessionKey);
        vm.expectRevert(
            abi.encodeWithSelector(
                TetherGuardHook.ExcessiveStepUpJump.selector,
                2.5 ether,
                2.2 ether
            )
        );
        hook.autonomousRadiusAdjustment(dynamicAccount, 2.5 ether, "Greedy jump");
    }

    function test_DynamicElasticity_CooldownActive_Reverts() public {
        address dynamicAccount = address(0xDD44);
        hook.initializeAccountPolicy(
            dynamicAccount,
            rootOwner,
            2.0 ether,
            TIER_GROWTH_DEFI,
            true,
            10.0 ether
        );

        vm.prank(rootOwner);
        hook.setSessionKeyAuthorization(dynamicAccount, sessionKey, true);

        vm.warp(block.timestamp + 1 days + 1);

        // First step-up: 2.0 ETH -> 2.2 ETH (Succeeds)
        vm.prank(sessionKey);
        hook.autonomousRadiusAdjustment(dynamicAccount, 2.2 ether, "First step up");

        // Attempting second step-up 2 hours later (Cooldown is 24 hours!) -> Must revert!
        vm.warp(block.timestamp + 2 hours);

        vm.prank(sessionKey);
        vm.expectRevert();
        hook.autonomousRadiusAdjustment(dynamicAccount, 2.3 ether, "Too fast second step up");
    }

    function test_DynamicElasticity_ExceedsCeiling_Reverts() public {
        // User opts in with 2 ETH radius, but hard ceiling is 2.1 ETH!
        address dynamicAccount = address(0xDD44);
        hook.initializeAccountPolicy(
            dynamicAccount,
            rootOwner,
            2.0 ether,
            TIER_GROWTH_DEFI,
            true,
            2.1 ether // Ceiling = 2.1 ETH
        );

        vm.prank(rootOwner);
        hook.setSessionKeyAuthorization(dynamicAccount, sessionKey, true);

        vm.warp(block.timestamp + 1 days + 1);

        // AI tries to step up to 2.2 ETH (10% jump, but EXCEEDS 2.1 ETH ceiling!)
        vm.prank(sessionKey);
        vm.expectRevert(
            abi.encodeWithSelector(
                TetherGuardHook.ExceedsElasticCeiling.selector,
                2.2 ether,
                2.1 ether
            )
        );
        hook.autonomousRadiusAdjustment(dynamicAccount, 2.2 ether, "Exceeds ceiling");
    }

    function test_VaultNative_CalibrateDynamicRadius_Succeeds() public {
        // Independent Vault-Native calibration (Zero input params from AI Brain!)
        address dynamicAccount = address(0xDD44);
        hook.initializeAccountPolicy(
            dynamicAccount,
            rootOwner,
            2.0 ether,
            TIER_GROWTH_DEFI,
            true,
            10.0 ether
        );

        vm.prank(rootOwner);
        hook.setSessionKeyAuthorization(dynamicAccount, sessionKey, true);
        vm.prank(rootOwner);
        hook.setTargetWhitelist(dynamicAccount, address(lidoStaking), true, TIER_GROWTH_DEFI);

        // 1. AI executes trade
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.2 ether), hex"");
        vm.prank(dynamicAccount);
        bytes memory hookData = hook.preCheck(sessionKey, 0.2 ether, msgData);
        vm.prank(dynamicAccount);
        hook.postCheck(hookData);

        // 2. User wakes up and ratifies it (incrementing on-chain consecutiveRatifications)
        vm.prank(rootOwner);
        hook.ratifyTransaction(dynamicAccount, 1);

        // 3. Fast forward 24 hours
        vm.warp(block.timestamp + 1 days + 1);

        // 4. Vault autonomously calibrates directly on-chain (+10% increase!)
        vm.prank(sessionKey);
        uint256 calibratedRadius = hook.calibrateDynamicRadius(dynamicAccount);

        assertEq(calibratedRadius, 2.2 ether); // Exactly 2.0 ETH + 10%
        TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(dynamicAccount);
        assertEq(p.tetherRadius, 2.2 ether);
    }

    function test_VaultNative_CalibrateDynamicRadius_ZeroRatifications_Reverts() public {
        address dynamicAccount = address(0xDD44);
        hook.initializeAccountPolicy(
            dynamicAccount,
            rootOwner,
            2.0 ether,
            TIER_GROWTH_DEFI,
            true,
            10.0 ether
        );

        vm.prank(rootOwner);
        hook.setSessionKeyAuthorization(dynamicAccount, sessionKey, true);

        vm.warp(block.timestamp + 1 days + 1);

        // No ratifications recorded on-chain -> Reverts!
        vm.prank(sessionKey);
        vm.expectRevert("INSUFFICIENT_RATIFICATIONS");
        hook.calibrateDynamicRadius(dynamicAccount);
    }

    function test_DynamicElasticity_DecreasingRadius_PermittedImmediately() public {
        address dynamicAccount = address(0xDD44);
        hook.initializeAccountPolicy(
            dynamicAccount,
            rootOwner,
            5.0 ether,
            TIER_GROWTH_DEFI,
            true,
            10.0 ether
        );

        vm.prank(rootOwner);
        hook.setSessionKeyAuthorization(dynamicAccount, sessionKey, true);

        // Market risk spikes: AI immediately dials radius down from 5 ETH -> 1 ETH
        // No cooldown required for reducing risk!
        vm.prank(sessionKey);
        hook.autonomousRadiusAdjustment(dynamicAccount, 1.0 ether, "Risk mitigation: dial down");

        TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(dynamicAccount);
        assertEq(p.tetherRadius, 1.0 ether);
    }

    // --- Asynchronous Morning Review Tests ---

    function test_MorningReview_LikeAndRatify_ReplenishesLimit() public {
        // AI executes a 0.3 ETH trade while user is inactive
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.3 ether), hex"");

        vm.prank(tecAccount);
        bytes memory hookData = hook.preCheck(sessionKey, 0.3 ether, msgData);

        vm.prank(tecAccount);
        hook.postCheck(hookData);

        // Verify transaction logged as PENDING_REVIEW
        TetherGuardHook.AutonomousExecutionRecord memory rec = hook.getExecutionRecord(tecAccount, 1);
        assertEq(rec.id, 1);
        assertEq(rec.target, address(lidoStaking));
        assertEq(rec.value, 0.3 ether);
        assertEq(uint8(rec.status), uint8(TetherGuardHook.ReviewStatus.PENDING_REVIEW));

        // Prior to review: dailySpent is 0.3 ETH, remaining radius is 0.2 ETH
        assertEq(hook.getRemainingRadius(tecAccount), 0.2 ether);

        // User wakes up in the morning and "Likes" (ratifies) the transaction!
        vm.prank(rootOwner);
        hook.ratifyTransaction(tecAccount, 1);

        // Status is now LIKED_AND_RATIFIED
        rec = hook.getExecutionRecord(tecAccount, 1);
        assertEq(uint8(rec.status), uint8(TetherGuardHook.ReviewStatus.LIKED_AND_RATIFIED));

        // Limit is replenished! dailySpent is 0, full 0.5 ETH radius is available again!
        TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(tecAccount);
        assertEq(p.dailySpent, 0);
        assertEq(hook.getRemainingRadius(tecAccount), TETHER_RADIUS);
    }

    function test_MorningReview_FlagForRevert_AppliesTrustPenalty() public {
        // AI executes 0.2 ETH trade
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.2 ether), hex"");

        vm.prank(tecAccount);
        bytes memory hookData = hook.preCheck(sessionKey, 0.2 ether, msgData);

        vm.prank(tecAccount);
        hook.postCheck(hookData);

        // User wakes up and objects: flags for cognitive unwind!
        vm.prank(rootOwner);
        hook.flagTransactionForRevert(tecAccount, 1, "Disliked: high slippage execution");

        TetherGuardHook.AutonomousExecutionRecord memory rec = hook.getExecutionRecord(tecAccount, 1);
        assertEq(uint8(rec.status), uint8(TetherGuardHook.ReviewStatus.REVERT_REQUESTED));
        assertEq(rec.userNote, "Disliked: high slippage execution");

        // Trust penalty applied: radius cut by 20% (0.5 ETH -> 0.4 ETH)
        TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(tecAccount);
        assertEq(p.tetherRadius, 0.4 ether);
    }

    function test_MorningReview_NoteWithPenalty() public {
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.2 ether), hex"");

        vm.prank(tecAccount);
        bytes memory hookData = hook.preCheck(sessionKey, 0.2 ether, msgData);

        vm.prank(tecAccount);
        hook.postCheck(hookData);

        // User submits note with vault penalty (10% penalty)
        vm.prank(rootOwner);
        hook.submitTransactionNote(tecAccount, 1, "Reduce staking during weekend volatility", true);

        TetherGuardHook.AutonomousExecutionRecord memory rec = hook.getExecutionRecord(tecAccount, 1);
        assertEq(uint8(rec.status), uint8(TetherGuardHook.ReviewStatus.NOTED));
        assertEq(rec.userNote, "Reduce staking during weekend volatility");

        // Radius cut by 10% (0.5 ETH -> 0.45 ETH)
        TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(tecAccount);
        assertEq(p.tetherRadius, 0.45 ether);
    }

    function test_MorningReview_NoteWithoutPenalty() public {
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.2 ether), hex"");

        vm.prank(tecAccount);
        bytes memory hookData = hook.preCheck(sessionKey, 0.2 ether, msgData);

        vm.prank(tecAccount);
        hook.postCheck(hookData);

        // User submits purely educational note without penalty
        vm.prank(rootOwner);
        hook.submitTransactionNote(tecAccount, 1, "Great swap timing, but prefer Curve over Lido next time", false);

        TetherGuardHook.AutonomousExecutionRecord memory rec = hook.getExecutionRecord(tecAccount, 1);
        assertEq(uint8(rec.status), uint8(TetherGuardHook.ReviewStatus.NOTED));

        // Radius remains unchanged
        TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(tecAccount);
        assertEq(p.tetherRadius, TETHER_RADIUS);
    }

    function test_MorningReview_AlreadyReviewed_Reverts() public {
        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.2 ether), hex"");

        vm.prank(tecAccount);
        bytes memory hookData = hook.preCheck(sessionKey, 0.2 ether, msgData);

        vm.prank(tecAccount);
        hook.postCheck(hookData);

        // First review
        vm.prank(rootOwner);
        hook.ratifyTransaction(tecAccount, 1);

        // Attempting to review again reverts!
        vm.prank(rootOwner);
        vm.expectRevert(
            abi.encodeWithSelector(
                TetherGuardHook.RecordAlreadyReviewed.selector,
                TetherGuardHook.ReviewStatus.LIKED_AND_RATIFIED
            )
        );
        hook.ratifyTransaction(tecAccount, 1);
    }
}




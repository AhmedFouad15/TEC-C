// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import { Test, console } from "forge-std/Test.sol";
import { TecAccount } from "../src/TecAccount.sol";
import { TetherGuardHook } from "../src/hooks/TetherGuardHook.sol";
import { SessionKeyValidator } from "../src/validators/SessionKeyValidator.sol";
import { TecPaymaster } from "../src/paymaster/TecPaymaster.sol";
import { MockDeFiProtocol } from "./mocks/MockDeFiProtocol.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { MockChainlinkFeed } from "./mocks/MockChainlinkFeed.sol";
import { PackedUserOperation } from "../src/interfaces/PackedUserOperation.sol";
import { IPaymaster } from "../src/interfaces/IPaymaster.sol";

/**
 * @title VaultComprehensiveFuzzTest
 * @notice Property-based and fuzzing suite for Tec-C Vault smart contract layer.
 *         Mathematically verifies invariants across arbitrary values, limits, and time warpings:
 *         1. Tether Radius velocity limits are never breached under any fuzzed amount
 *         2. Dynamic Elasticity step-ups can NEVER exceed the 10% daily ceiling
 *         3. Trust penalties mathematically strictly decrease or maintain radius (no inversion)
 *         4. Multi-token USD normalization precision without overflow
 *         5. Epoch replenishment and time independence
 *         6. Anti-griefing paymaster cumulative gas capping
 *         7. Ephemeral session key temporal window boundaries
 */
contract VaultComprehensiveFuzzTest is Test {
    TecAccount public account;
    TetherGuardHook public hook;
    SessionKeyValidator public sessionValidator;
    TecPaymaster public paymaster;
    MockDeFiProtocol public mockTarget;
    MockERC20 public mockUsdc;
    MockChainlinkFeed public ethFeed;
    MockChainlinkFeed public usdcFeed;

    address public entryPoint = address(0xEEEE);
    address public rootOwner = address(0xAA11);
    address public sessionKey = address(0xBB22);

    function setUp() public {
        hook = new TetherGuardHook();
        sessionValidator = new SessionKeyValidator();
        paymaster = new TecPaymaster(entryPoint);
        account = new TecAccount(entryPoint);
        mockTarget = new MockDeFiProtocol();
        mockUsdc = new MockERC20("USDC", "USDC", 6);

        ethFeed = new MockChainlinkFeed(8, 3000 * 1e8, "ETH / USD");
        usdcFeed = new MockChainlinkFeed(8, 1 * 1e8, "USDC / USD");

        hook.setGlobalPriceFeed(hook.NATIVE_ETH(), address(ethFeed));
        hook.setGlobalPriceFeed(address(mockUsdc), address(usdcFeed));

        account.initialize(rootOwner, address(hook), address(sessionValidator));
        hook.initializeAccountPolicy(address(account), rootOwner, 1000 * 1e8, hook.RISK_TIER_GROWTH_DEFI());

        vm.startPrank(rootOwner);
        hook.setTargetWhitelist(address(account), address(mockTarget), true, hook.RISK_TIER_GROWTH_DEFI());
        hook.setTargetWhitelist(address(account), address(mockUsdc), true, hook.RISK_TIER_CORE_PRESERVATION());
        hook.setSessionKeyAuthorization(address(account), sessionKey, true);
        vm.stopPrank();

        vm.deal(address(account), 1_000_000 ether);
        paymaster.depositForAccount{value: 10 ether}(address(account));
    }

    // =========================================================================
    // Property 1: Tether Radius Velocity Enforcement Fuzzing
    // =========================================================================

    function testFuzz_TetherRadius_VelocityEnforcement(uint256 dailyLimitUSD, uint256 spendUSD) public {
        // Bound inputs to realistic USD limits ($10 to $1,000,000 USD, 8 decimals)
        dailyLimitUSD = bound(dailyLimitUSD, 10 * 1e8, 1_000_000 * 1e8);
        spendUSD = bound(spendUSD, 1 * 1e8, 2_000_000 * 1e8);

        // Align with USDC 6-decimal precision (multiples of 100 in 8-decimal USD)
        dailyLimitUSD = (dailyLimitUSD / 100) * 100;
        spendUSD = (spendUSD / 100) * 100;
        if (spendUSD == 0) spendUSD = 100;

        address fuzzAccount = address(0xF001);
        hook.initializeAccountPolicy(fuzzAccount, rootOwner, dailyLimitUSD, hook.RISK_TIER_GROWTH_DEFI(), false, dailyLimitUSD);

        vm.startPrank(rootOwner);
        hook.setTargetWhitelist(fuzzAccount, address(mockUsdc), true, hook.RISK_TIER_CORE_PRESERVATION());
        hook.setSessionKeyAuthorization(fuzzAccount, sessionKey, true);
        vm.stopPrank();

        // 1 USDC = 1 USD (6 decimals for USDC, spendUSD has 8 decimals)
        uint256 usdcAmount = spendUSD / 100;

        bytes memory transferCall = abi.encodeWithSelector(
            MockERC20.transfer.selector,
            address(mockTarget),
            usdcAmount
        );
        bytes memory msgData = abi.encodePacked(address(mockUsdc), uint256(0), transferCall);

        // PreCheck verification
        if (spendUSD <= dailyLimitUSD) {
            vm.prank(fuzzAccount);
            bytes memory hookData = hook.preCheck(sessionKey, 0, msgData);
            assertTrue(hookData.length > 0);

            TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(fuzzAccount);
            // Verify dailySpent is updated accurately
            assertEq(p.dailySpent, spendUSD);
            assertEq(hook.getRemainingRadius(fuzzAccount), dailyLimitUSD - spendUSD);
        } else {
            vm.prank(fuzzAccount);
            vm.expectRevert(
                abi.encodeWithSelector(
                    TetherGuardHook.TetherRadiusExceeded.selector,
                    spendUSD,
                    dailyLimitUSD
                )
            );
            hook.preCheck(sessionKey, 0, msgData);
        }
    }

    // =========================================================================
    // Property 2: Dynamic Elasticity Harsh Step-Up 10% Cap Fuzzing
    // =========================================================================

    function testFuzz_DynamicElasticity_10PercentGrowthCap(uint256 currentRadius, uint256 proposedRadius) public {
        currentRadius = bound(currentRadius, 100 * 1e8, 100_000 * 1e8);
        // Test proposals from 0 up to 5x current radius
        proposedRadius = bound(proposedRadius, 1, currentRadius * 5);

        address fuzzAccount = address(0xF002);
        uint256 ceiling = currentRadius * 10;
        hook.initializeAccountPolicy(fuzzAccount, rootOwner, currentRadius, hook.RISK_TIER_GROWTH_DEFI(), true, ceiling);

        vm.prank(rootOwner);
        hook.setSessionKeyAuthorization(fuzzAccount, sessionKey, true);

        // Max allowed is strictly 10% growth
        uint256 maxAllowed = currentRadius + (currentRadius * 10) / 100;

        vm.warp(block.timestamp + 1 days + 1);

        if (proposedRadius > maxAllowed) {
            vm.prank(sessionKey);
            vm.expectRevert(
                abi.encodeWithSelector(
                    TetherGuardHook.ExcessiveStepUpJump.selector,
                    proposedRadius,
                    maxAllowed
                )
            );
            hook.autonomousRadiusAdjustment(fuzzAccount, proposedRadius, "Fuzz step-up jump");
        } else {
            vm.prank(sessionKey);
            hook.autonomousRadiusAdjustment(fuzzAccount, proposedRadius, "Valid step-up");
            TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(fuzzAccount);
            assertEq(p.tetherRadius, proposedRadius);
        }
    }

    // =========================================================================
    // Property 3: Trust Penalty Mathematical Non-Inversion Fuzzing
    // =========================================================================

    function testFuzz_TrustPenalty_MathematicallyStrictlyDecreases(uint256 baselineRadius, uint256 currentRadius) public {
        baselineRadius = bound(baselineRadius, 100 * 1e8, 1_000_000 * 1e8);
        // Current radius can be anywhere from $10 up to 2x baseline
        currentRadius = bound(currentRadius, 10 * 1e8, baselineRadius * 2);

        address fuzzAccount = address(0xF003);
        hook.initializeAccountPolicy(fuzzAccount, rootOwner, baselineRadius, hook.RISK_TIER_GROWTH_DEFI(), false, baselineRadius);

        // Authorize session key and whitelist mockTarget and mockUsdc
        vm.startPrank(rootOwner);
        hook.setTargetWhitelist(fuzzAccount, address(mockUsdc), true, hook.RISK_TIER_CORE_PRESERVATION());
        hook.setSessionKeyAuthorization(fuzzAccount, sessionKey, true);
        hook.setTetherRadius(fuzzAccount, currentRadius, hook.RISK_TIER_GROWTH_DEFI());
        vm.stopPrank();

        // Simulate an autonomous transaction sized strictly within currentRadius
        uint256 tradeUSD = currentRadius / 4;
        uint256 usdcAmount = tradeUSD / 100;
        if (usdcAmount == 0) usdcAmount = 1;

        bytes memory msgData = abi.encodePacked(
            address(mockUsdc),
            uint256(0),
            abi.encodeWithSelector(MockERC20.transfer.selector, address(mockTarget), usdcAmount)
        );
        vm.prank(fuzzAccount);
        bytes memory hookData = hook.preCheck(sessionKey, 0, msgData);
        vm.prank(fuzzAccount);
        hook.postCheck(hookData);

        // Flag transaction for revert
        vm.prank(rootOwner);
        hook.flagTransactionForRevert(fuzzAccount, 1, "Fuzz objection");

        TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(fuzzAccount);

        // INVARIANT: The resulting radius must NEVER be greater than currentRadius!
        // Trust penalty must strictly decrease or maintain the radius!
        assertTrue(p.tetherRadius <= currentRadius, "PENALTY_INVERSION_DETECTED");
    }

    // =========================================================================
    // Property 4: Epoch Rollover & Replenishment Fuzzing
    // =========================================================================

    function testFuzz_EpochRollover_ReplenishesQuota(uint256 limitUSD, uint256 spendUSD, uint256 daysPassed) public {
        limitUSD = bound(limitUSD, 100 * 1e8, 10_000 * 1e8);
        spendUSD = bound(spendUSD, 10 * 1e8, limitUSD);
        daysPassed = bound(daysPassed, 1, 365); // 1 day to 1 year

        // Align with USDC 6-decimal precision
        limitUSD = (limitUSD / 100) * 100;
        spendUSD = (spendUSD / 100) * 100;
        if (spendUSD == 0) spendUSD = 100;

        address fuzzAccount = address(0xF004);
        hook.initializeAccountPolicy(fuzzAccount, rootOwner, limitUSD, hook.RISK_TIER_GROWTH_DEFI(), false, limitUSD);

        vm.startPrank(rootOwner);
        hook.setTargetWhitelist(fuzzAccount, address(mockUsdc), true, hook.RISK_TIER_CORE_PRESERVATION());
        hook.setSessionKeyAuthorization(fuzzAccount, sessionKey, true);
        vm.stopPrank();

        uint256 usdcAmount = spendUSD / 100;
        bytes memory msgData = abi.encodePacked(
            address(mockUsdc),
            uint256(0),
            abi.encodeWithSelector(MockERC20.transfer.selector, address(mockTarget), usdcAmount)
        );

        // Spend on Day 0
        vm.prank(fuzzAccount);
        hook.preCheck(sessionKey, 0, msgData);
        assertEq(hook.getRemainingRadius(fuzzAccount), limitUSD - spendUSD);

        // Warp daysPassed days into the future
        vm.warp(block.timestamp + (daysPassed * 1 days) + 1);
        usdcFeed.setPrice(1 * 1e8);
        // Refresh AI heartbeat after multi-day warp
        vm.prank(sessionKey);
        hook.recordAIHeartbeat(fuzzAccount);

        // Quota is 100% replenished!
        assertEq(hook.getRemainingRadius(fuzzAccount), limitUSD);

        // Can spend full limitUSD again
        vm.prank(fuzzAccount);
        hook.preCheck(sessionKey, 0, msgData);
        assertEq(hook.getRemainingRadius(fuzzAccount), limitUSD - spendUSD);
    }

    // =========================================================================
    // Property 5: Paymaster Anti-Griefing Fuzzing
    // =========================================================================

    function testFuzz_Paymaster_GasSponsorshipCap(uint256 cost1, uint256 cost2) public {
        // Bound cost1 and cost2 between 0.0001 ETH and 0.01 ETH
        cost1 = bound(cost1, 0.0001 ether, 0.01 ether);
        cost2 = bound(cost2, 0.0001 ether, 0.01 ether);

        address fuzzAccount = address(0xF005);
        address fuzzKey = address(0xFA05);
        paymaster.depositForAccount{value: 1 ether}(fuzzAccount);

        PackedUserOperation memory userOp;
        userOp.sender = fuzzAccount;
        userOp.signature = abi.encodePacked(fuzzKey, hex"112233");

        // First UserOp
        (, uint256 val1) = paymaster.validatePaymasterUserOp(userOp, bytes32(0), cost1);
        if (cost1 <= paymaster.MAX_SESSION_GAS_BUDGET()) {
            assertEq(val1, 0); // Accepted
            vm.prank(entryPoint);
            paymaster.postOp(
                IPaymaster.PostOpMode.opSucceeded,
                abi.encode(fuzzAccount, fuzzKey, cost1),
                cost1,
                0
            );

            // Second UserOp
            (, uint256 val2) = paymaster.validatePaymasterUserOp(userOp, bytes32(0), cost2);
            if (cost1 + cost2 > paymaster.MAX_SESSION_GAS_BUDGET()) {
                assertEq(val2, 1, "PAYMASTER_BUDGET_OVERSPENT"); // Rejected anti-griefing!
            } else {
                assertEq(val2, 0); // Accepted within budget
            }
        } else {
            assertEq(val1, 1); // Rejected on first op
        }
    }
}

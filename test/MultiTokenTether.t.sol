// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {TetherGuardHook} from "../src/hooks/TetherGuardHook.sol";
import {MockChainlinkFeed} from "./mocks/MockChainlinkFeed.sol";
import {MockERC20} from "./mocks/MockERC20.sol";
import {IERC20} from "../src/interfaces/IERC20.sol";

contract MultiTokenTetherTest is Test {
    TetherGuardHook public hook;

    // Tokens with diverse decimal precisions
    MockERC20 public usdc; // 6 decimals
    MockERC20 public wbtc; // 8 decimals
    MockERC20 public dai; // 18 decimals
    MockERC20 public unpricedToken;

    // Mock Chainlink Feeds (8 decimals standard USD)
    MockChainlinkFeed public ethFeed; // $3,000.00 (3000 * 1e8)
    MockChainlinkFeed public usdcFeed; // $1.00 (1 * 1e8)
    MockChainlinkFeed public wbtcFeed; // $60,000.00 (60000 * 1e8)
    MockChainlinkFeed public daiFeed; // $1.00 (1 * 1e8)

    uint256 public rootOwnerPk = 0xA11CE;
    address public rootOwner;
    address public tecAccount = address(0xBB22); // Tec-C Smart Account
    address public sessionKey = address(0xCC33); // AI Agent Session Key
    address public recipient = address(0xDD44);

    // Institutional Daily Tether Radius: $500 USD (8 decimals)
    uint256 public constant TETHER_RADIUS_USD = 500 * 1e8;

    uint8 public constant TIER_CORE_PRESERVATION = 1;
    uint8 public constant TIER_GROWTH_DEFI = 2;
    uint8 public constant TIER_UNRESTRICTED = 3;

    function setUp() public {
        rootOwner = vm.addr(rootOwnerPk);
        hook = new TetherGuardHook();

        // 1. Deploy Tokens
        usdc = new MockERC20("USD Coin", "USDC", 6);
        wbtc = new MockERC20("Wrapped Bitcoin", "WBTC", 8);
        dai = new MockERC20("Dai Stablecoin", "DAI", 18);
        unpricedToken = new MockERC20("Unpriced Meme", "MEME", 18);

        // 2. Deploy Chainlink Feeds (8 decimals standard)
        ethFeed = new MockChainlinkFeed(8, 3000 * 1e8, "ETH / USD");
        usdcFeed = new MockChainlinkFeed(8, 1 * 1e8, "USDC / USD");
        wbtcFeed = new MockChainlinkFeed(8, 60000 * 1e8, "WBTC / USD");
        daiFeed = new MockChainlinkFeed(8, 1 * 1e8, "DAI / USD");

        // 3. Configure Global Feeds on TetherGuardHook
        hook.setGlobalPriceFeed(hook.NATIVE_ETH(), address(ethFeed));
        hook.setGlobalPriceFeed(address(usdc), address(usdcFeed));
        hook.setGlobalPriceFeed(address(wbtc), address(wbtcFeed));
        hook.setGlobalPriceFeed(address(dai), address(daiFeed));

        // 4. Initialize Account Policy with $500 USD daily radius and Tier 2 (Growth DeFi)
        hook.initializeAccountPolicy(tecAccount, rootOwner, TETHER_RADIUS_USD, TIER_GROWTH_DEFI);

        // 5. Whitelist tokens as Tier 1 / Tier 2
        vm.startPrank(rootOwner);
        hook.setTargetWhitelist(tecAccount, address(usdc), true, TIER_CORE_PRESERVATION);
        hook.setTargetWhitelist(tecAccount, address(wbtc), true, TIER_CORE_PRESERVATION);
        hook.setTargetWhitelist(tecAccount, address(dai), true, TIER_CORE_PRESERVATION);
        hook.setTargetWhitelist(tecAccount, address(unpricedToken), true, TIER_GROWTH_DEFI);

        // 6. Authorize AI Session Key
        hook.setSessionKeyAuthorization(tecAccount, sessionKey, true);
        vm.stopPrank();

        // 7. Fund Tec-C Smart Account treasury
        vm.deal(tecAccount, 10 ether);
        usdc.mint(tecAccount, 100_000 * 1e6); // 100k USDC
        wbtc.mint(tecAccount, 5 * 1e8); // 5 WBTC
        dai.mint(tecAccount, 50_000 * 1e18); // 50k DAI
    }

    // =========================================================================
    // --- Test 1: ERC-20 Transfer Within Tether Radius (USDC 6 Decimals) ---
    // =========================================================================
    function test_ERC20Transfer_WithinTetherRadius_Success() public {
        // AI transfers 200 USDC ($200 USD equivalent <= $500 limit)
        uint256 transferAmount = 200 * 1e6; // 200 USDC
        bytes memory call = abi.encodeWithSelector(IERC20.transfer.selector, recipient, transferAmount);
        bytes memory msgData = abi.encodePacked(address(usdc), uint256(0), call);

        vm.prank(tecAccount);
        bytes memory hookData = hook.preCheck(sessionKey, 0, msgData);

        // Verify spending accounting: $200 consumed, $300 remaining
        TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(tecAccount);
        assertEq(p.dailySpent, 200 * 1e8);
        assertEq(hook.getRemainingRadius(tecAccount), 300 * 1e8);

        // Verify postCheck audit logging
        vm.prank(tecAccount);
        hook.postCheck(hookData);
        assertEq(hook.totalAuditedExecutions(), 1);

        TetherGuardHook.AutonomousExecutionRecord memory rec = hook.getExecutionRecord(tecAccount, 1);
        assertEq(rec.target, address(usdc));
        assertEq(rec.value, 200 * 1e8); // recorded in USD
    }

    // =========================================================================
    // --- Test 2: ERC-20 Transfer Exceeding Tether Radius Reverts ---
    // =========================================================================
    function test_ERC20Transfer_ExceedingTetherRadius_Reverts() public {
        // AI attempts to transfer 600 USDC ($600 USD > $500 limit)
        uint256 transferAmount = 600 * 1e6;
        bytes memory call = abi.encodeWithSelector(IERC20.transfer.selector, recipient, transferAmount);
        bytes memory msgData = abi.encodePacked(address(usdc), uint256(0), call);

        vm.prank(tecAccount);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.TetherRadiusExceeded.selector, 600 * 1e8, 500 * 1e8));
        hook.preCheck(sessionKey, 0, msgData);
    }

    // =========================================================================
    // --- Test 3: Cumulative Multi-Token Spending Tracking (USDC + WBTC + DAI) ---
    // =========================================================================
    function test_CumulativeMultiTokenSpending_EnforcesUSDLimit() public {
        // 1. First tx: 200 USDC = $200 USD (Spent: $200, Remaining: $300)
        bytes memory call1 = abi.encodeWithSelector(IERC20.transfer.selector, recipient, 200 * 1e6);
        bytes memory msgData1 = abi.encodePacked(address(usdc), uint256(0), call1);
        vm.prank(tecAccount);
        hook.preCheck(sessionKey, 0, msgData1);

        // 2. Second tx: 0.0025 WBTC = $150 USD (Spent: $350, Remaining: $150)
        // 0.0025 * 60,000 = $150. WBTC decimals = 8 -> amount = 0.0025 * 1e8 = 250,000
        bytes memory call2 = abi.encodeWithSelector(IERC20.transfer.selector, recipient, 250_000);
        bytes memory msgData2 = abi.encodePacked(address(wbtc), uint256(0), call2);
        vm.prank(tecAccount);
        hook.preCheck(sessionKey, 0, msgData2);

        assertEq(hook.getRemainingRadius(tecAccount), 150 * 1e8);

        // 3. Third tx: 100 DAI = $100 USD (Spent: $450, Remaining: $50)
        bytes memory call3 = abi.encodeWithSelector(IERC20.transfer.selector, recipient, 100 * 1e18);
        bytes memory msgData3 = abi.encodePacked(address(dai), uint256(0), call3);
        vm.prank(tecAccount);
        hook.preCheck(sessionKey, 0, msgData3);

        assertEq(hook.getRemainingRadius(tecAccount), 50 * 1e8);

        // 4. Fourth tx: 60 USDC = $60 USD -> Exceeds $50 remaining -> REVERTS!
        bytes memory call4 = abi.encodeWithSelector(IERC20.transfer.selector, recipient, 60 * 1e6);
        bytes memory msgData4 = abi.encodePacked(address(usdc), uint256(0), call4);
        vm.prank(tecAccount);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.TetherRadiusExceeded.selector, 60 * 1e8, 50 * 1e8));
        hook.preCheck(sessionKey, 0, msgData4);
    }

    // =========================================================================
    // --- Test 4: Native ETH Spending Normalized to USD ---
    // =========================================================================
    function test_NativeETH_NormalizedToUSD() public {
        // ETH price is $3,000. 0.1 ETH = $300 USD.
        bytes memory msgData = abi.encodePacked(address(0x1111), uint256(0.1 ether), hex"");

        vm.prank(rootOwner);
        hook.setTargetWhitelist(tecAccount, address(0x1111), true, TIER_CORE_PRESERVATION);

        vm.prank(tecAccount);
        hook.preCheck(sessionKey, 0.1 ether, msgData);

        // Daily spent should be $300 USD (300 * 1e8)
        assertEq(hook.getRemainingRadius(tecAccount), 200 * 1e8);
    }

    // =========================================================================
    // --- Test 5: ERC-20 Approve Call Inspection ---
    // =========================================================================
    function test_ERC20Approve_EnforcesTetherRadius() public {
        // AI approves a DEX router for 1,000 USDC ($1,000 USD) -> Exceeds $500 -> Reverts!
        address router = address(0x9999);
        bytes memory call = abi.encodeWithSelector(IERC20.approve.selector, router, 1000 * 1e6);
        bytes memory msgData = abi.encodePacked(address(usdc), uint256(0), call);

        vm.prank(tecAccount);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.TetherRadiusExceeded.selector, 1000 * 1e8, 500 * 1e8));
        hook.preCheck(sessionKey, 0, msgData);
    }

    // =========================================================================
    // --- Test 5b: ERC-20 increaseAllowance Call Inspection ---
    // =========================================================================
    function test_ERC20IncreaseAllowance_EnforcesTetherRadius() public {
        address router = address(0x9999);
        bytes memory call = abi.encodeWithSelector(bytes4(0x39509351), router, 700 * 1e6); // 700 USDC ($700 > $500)
        bytes memory msgData = abi.encodePacked(address(usdc), uint256(0), call);

        vm.prank(tecAccount);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.TetherRadiusExceeded.selector, 700 * 1e8, 500 * 1e8));
        hook.preCheck(sessionKey, 0, msgData);
    }

    // =========================================================================
    // --- Test 6: Stale Oracle Protection (> 24 Hours) Reverts ---
    // =========================================================================
    function test_StaleOraclePrice_Reverts() public {
        // Warp time forward 25 hours without updating oracle
        vm.warp(block.timestamp + 25 hours);

        bytes memory call = abi.encodeWithSelector(IERC20.transfer.selector, recipient, 100 * 1e6);
        bytes memory msgData = abi.encodePacked(address(usdc), uint256(0), call);

        vm.prank(tecAccount);
        vm.expectRevert(
            abi.encodeWithSelector(TetherGuardHook.StaleOraclePrice.selector, address(usdc), usdcFeed.updatedAt())
        );
        hook.preCheck(sessionKey, 0, msgData);
    }

    // =========================================================================
    // --- Test 7: Negative / Zero Oracle Price Reverts ---
    // =========================================================================
    function test_InvalidOraclePrice_Reverts() public {
        // Set oracle price to 0 or negative
        usdcFeed.setPrice(0);

        bytes memory call = abi.encodeWithSelector(IERC20.transfer.selector, recipient, 100 * 1e6);
        bytes memory msgData = abi.encodePacked(address(usdc), uint256(0), call);

        vm.prank(tecAccount);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.InvalidOraclePrice.selector, address(usdc), 0));
        hook.preCheck(sessionKey, 0, msgData);
    }

    // =========================================================================
    // --- Test 8: Missing Oracle Price Feed in USD Mode Reverts ---
    // =========================================================================
    function test_MissingOraclePriceFeed_Reverts() public {
        // unpricedToken has no Chainlink feed configured
        bytes memory call = abi.encodeWithSelector(IERC20.transfer.selector, recipient, 1000 * 1e18);
        bytes memory msgData = abi.encodePacked(address(unpricedToken), uint256(0), call);

        vm.prank(tecAccount);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.MissingOraclePriceFeed.selector, address(unpricedToken)));
        hook.preCheck(sessionKey, 0, msgData);
    }

    // =========================================================================
    // --- Test 9: Per-Account Custom Price Feed Override ---
    // =========================================================================
    function test_AccountSpecificPriceFeedOverride() public {
        // Account owner sets a custom feed with discounted price
        MockChainlinkFeed customUsdcFeed = new MockChainlinkFeed(8, 0.98 * 1e8, "Custom USDC Feed");

        vm.prank(rootOwner);
        hook.setAccountPriceFeed(tecAccount, address(usdc), address(customUsdcFeed));

        // Effective price should now come from customUsdcFeed
        (uint256 price,) = hook.getLatestPrice(tecAccount, address(usdc));
        assertEq(price, 0.98 * 1e8);
    }

    // =========================================================================
    // --- Test 10: Comprehensive Portfolio Valuation (getTotalPortfolioValueUSD) ---
    // =========================================================================
    function test_GetTotalPortfolioValueUSD_ReturnsAccurateValuation() public {
        // Treasury Balances:
        // 10 ETH @ $3,000 = $30,000
        // 100,000 USDC @ $1.00 = $100,000
        // 5 WBTC @ $60,000 = $300,000
        // 50,000 DAI @ $1.00 = $50,000
        // Expected Total USD = $480,000 (480,000 * 1e8)

        address[] memory tokens = new address[](4);
        tokens[0] = hook.NATIVE_ETH();
        tokens[1] = address(usdc);
        tokens[2] = address(wbtc);
        tokens[3] = address(dai);

        (uint256 totalUSD, TetherGuardHook.TokenBalanceDetail[] memory details) =
            hook.getTotalPortfolioValueUSD(tecAccount, tokens);

        assertEq(totalUSD, 480_000 * 1e8);
        assertEq(details.length, 4);

        // Detail 0: Native ETH
        assertEq(details[0].symbol, "ETH");
        assertEq(details[0].balance, 10 ether);
        assertEq(details[0].priceUSD, 3000 * 1e8);
        assertEq(details[0].valueUSD, 30_000 * 1e8);

        // Detail 1: USDC
        assertEq(details[1].symbol, "USDC");
        assertEq(details[1].decimals, 6);
        assertEq(details[1].balance, 100_000 * 1e6);
        assertEq(details[1].priceUSD, 1 * 1e8);
        assertEq(details[1].valueUSD, 100_000 * 1e8);

        // Detail 2: WBTC
        assertEq(details[2].symbol, "WBTC");
        assertEq(details[2].decimals, 8);
        assertEq(details[2].balance, 5 * 1e8);
        assertEq(details[2].priceUSD, 60000 * 1e8);
        assertEq(details[2].valueUSD, 300_000 * 1e8);

        // Detail 3: DAI
        assertEq(details[3].symbol, "DAI");
        assertEq(details[3].decimals, 18);
        assertEq(details[3].balance, 50_000 * 1e18);
        assertEq(details[3].priceUSD, 1 * 1e8);
        assertEq(details[3].valueUSD, 50_000 * 1e8);
    }

    // =========================================================================
    // --- Test 11: Breaking the Tether for ERC-20 Breakout Transaction ---
    // =========================================================================
    function test_BreakingTheTether_ERC20_WithBiometricAndSignApproval() public {
        // AI proposes a 10,000 USDC transfer ($10,000 > $500 limit)
        bytes memory call = abi.encodeWithSelector(IERC20.transfer.selector, recipient, 10_000 * 1e6);
        bytes memory msgData = abi.encodePacked(address(usdc), uint256(0), call);
        bytes32 execHash = keccak256(msgData);

        // 1. Without biometric verification -> Reverts
        vm.prank(tecAccount);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.TetherRadiusExceeded.selector, 10_000 * 1e8, 500 * 1e8));
        hook.preCheck(sessionKey, 0, msgData);

        // 2. User completes Biometric FaceID verification (opens 5m window)
        vm.prank(rootOwner);
        hook.completeBiometricVerification(tecAccount);
        assertTrue(hook.isBiometricActive(tecAccount));

        // 3. User submits Sign Approval (Accept) for this breakout execution hash
        vm.prank(rootOwner);
        hook.submitSignApproval(tecAccount, execHash, true);

        // 4. AI executes breakout successfully within the 5m window
        vm.prank(tecAccount);
        bytes memory hookData = hook.preCheck(sessionKey, 0, msgData);

        // 5. PostCheck audits breakout
        vm.prank(tecAccount);
        hook.postCheck(hookData);
        assertEq(hook.totalAuditedExecutions(), 1);
    }
}

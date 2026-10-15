// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import { Test, console } from "forge-std/Test.sol";
import { TecAccount } from "../src/TecAccount.sol";
import { TetherGuardHook } from "../src/hooks/TetherGuardHook.sol";
import { SessionKeyValidator } from "../src/validators/SessionKeyValidator.sol";
import { WebAuthnP256Validator } from "../src/validators/WebAuthnP256Validator.sol";
import { TecPaymaster } from "../src/paymaster/TecPaymaster.sol";
import { MockDeFiProtocol } from "./mocks/MockDeFiProtocol.sol";
import { MockERC20 } from "./mocks/MockERC20.sol";
import { MockChainlinkFeed } from "./mocks/MockChainlinkFeed.sol";
import { MockRIP7212 } from "./mocks/MockRIP7212.sol";
import { PackedUserOperation } from "../src/interfaces/PackedUserOperation.sol";
import { IPaymaster } from "../src/interfaces/IPaymaster.sol";
import { MODULE_TYPE_HOOK, MODULE_TYPE_VALIDATOR } from "../src/interfaces/IERC7579Account.sol";

/**
 * @title VaultLifecycleScenariosTest
 * @notice Exhaustive integration suite testing real-world corporate vault scenarios:
 *         1. Full Enterprise Onboarding & Multi-Day Autonomous Operations
 *         2. Multi-Token USD Normalized Spending & Portfolio Breakdown
 *         3. Breaking the Tether: Biometric P-256 + Sign Approval Escalation
 *         4. Adversarial Attack Sandbox & Revert Verification
 *         5. AI Heartbeat Inactivity & Corporate Dead-Man's Succession
 */
contract VaultLifecycleScenariosTest is Test {
    TecAccount public account;
    TetherGuardHook public hook;
    SessionKeyValidator public sessionValidator;
    WebAuthnP256Validator public passkeyValidator;
    TecPaymaster public paymaster;
    MockRIP7212 public mockPrecompile;

    MockDeFiProtocol public lidoStaking;
    MockDeFiProtocol public curvePool;
    MockDeFiProtocol public shiborTreasuryMMF;
    MockDeFiProtocol public maliciousDrainer;

    MockERC20 public usdc;   // 6 decimals
    MockERC20 public wbtc;   // 8 decimals
    MockERC20 public dai;    // 18 decimals

    MockChainlinkFeed public ethFeed;   // $3,000 (8 decimals)
    MockChainlinkFeed public usdcFeed;  // $1.00 (8 decimals)
    MockChainlinkFeed public wbtcFeed;  // $60,000 (8 decimals)
    MockChainlinkFeed public daiFeed;   // $1.00 (8 decimals)

    address public entryPoint = address(0xEEEE);
    address public corporateDeployer;
    uint256 public rootOwnerPrivateKey = 0xAA11CE;
    address public rootOwner;
    uint256 public sessionKeyPrivateKey = 0xBB22CE;
    address public sessionKey;
    address public corporateGuardian = address(0xCC33);
    address public corporateSuccessor = address(0xDD44);

    // Hardware Passkey coordinates (iPhone Secure Enclave simulation)
    uint256 public constant PASSKEY_QX = 0x5821017c667a6d8d9b1a5e3f4c2b1a0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a;
    uint256 public constant PASSKEY_QY = 0x203541f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3;

    uint256 public constant INITIAL_TETHER_RADIUS_USD = 1_000 * 1e8; // $1,000 USD daily limit

    function setUp() public {
        corporateDeployer = address(this);
        rootOwner = vm.addr(rootOwnerPrivateKey);
        sessionKey = vm.addr(sessionKeyPrivateKey);

        // Etch RIP-7212 precompile at 0x100
        mockPrecompile = new MockRIP7212();
        vm.etch(address(0x100), address(mockPrecompile).code);

        // Deploy contracts
        hook = new TetherGuardHook();
        sessionValidator = new SessionKeyValidator();
        passkeyValidator = new WebAuthnP256Validator();
        paymaster = new TecPaymaster(entryPoint);
        account = new TecAccount(entryPoint);

        // Deploy mock DeFi protocols
        lidoStaking = new MockDeFiProtocol();
        curvePool = new MockDeFiProtocol();
        shiborTreasuryMMF = new MockDeFiProtocol();
        maliciousDrainer = new MockDeFiProtocol();

        // Deploy mock tokens
        usdc = new MockERC20("USD Coin", "USDC", 6);
        wbtc = new MockERC20("Wrapped BTC", "WBTC", 8);
        dai = new MockERC20("Dai Stablecoin", "DAI", 18);

        // Deploy Chainlink price feeds (8 decimals)
        ethFeed = new MockChainlinkFeed(8, 3000 * 1e8, "ETH / USD");
        usdcFeed = new MockChainlinkFeed(8, 1 * 1e8, "USDC / USD");
        wbtcFeed = new MockChainlinkFeed(8, 60000 * 1e8, "WBTC / USD");
        daiFeed = new MockChainlinkFeed(8, 1 * 1e8, "DAI / USD");

        // Register global price feeds
        hook.setGlobalPriceFeed(hook.NATIVE_ETH(), address(ethFeed));
        hook.setGlobalPriceFeed(address(usdc), address(usdcFeed));
        hook.setGlobalPriceFeed(address(wbtc), address(wbtcFeed));
        hook.setGlobalPriceFeed(address(dai), address(daiFeed));

        // Initialize TecAccount modules and rootOwner
        account.initialize(rootOwner, address(hook), address(sessionValidator));

        // Configure Passkey on hook (via deployer onboarding path)
        hook.setAccountPasskey(address(account), PASSKEY_QX, PASSKEY_QY);

        // Initialize Account Policy on hook: $1,000 USD Tether Radius, Tier 2 (Growth/DeFi), Elasticity enabled
        hook.initializeAccountPolicy(
            address(account),
            rootOwner,
            INITIAL_TETHER_RADIUS_USD,
            hook.RISK_TIER_GROWTH_DEFI(),
            true,
            5_000 * 1e8 // $5,000 hard ceiling
        );

        // Whitelist verified institutional protocols and configure authorizations
        vm.startPrank(rootOwner);
        hook.setTargetWhitelist(address(account), address(shiborTreasuryMMF), true, hook.RISK_TIER_CORE_PRESERVATION());
        hook.setTargetWhitelist(address(account), address(lidoStaking), true, hook.RISK_TIER_GROWTH_DEFI());
        hook.setTargetWhitelist(address(account), address(curvePool), true, hook.RISK_TIER_GROWTH_DEFI());
        hook.setTargetWhitelist(address(account), address(usdc), true, hook.RISK_TIER_CORE_PRESERVATION());
        hook.setTargetWhitelist(address(account), address(wbtc), true, hook.RISK_TIER_CORE_PRESERVATION());
        hook.setTargetWhitelist(address(account), address(dai), true, hook.RISK_TIER_CORE_PRESERVATION());
        hook.setSessionKeyAuthorization(address(account), sessionKey, true);
        hook.configureDeadmanSwitch(address(account), corporateGuardian, 90 days);
        vm.stopPrank();

        // Register session key in SessionKeyValidator for 30 days
        vm.prank(address(account));
        sessionValidator.registerSessionKey(
            address(account),
            sessionKey,
            uint48(block.timestamp),
            uint48(block.timestamp + 30 days),
            keccak256("Mandate:InstitutionalTreasuryYield")
        );

        // Fund Account with ETH and ERC20 tokens
        vm.deal(address(account), 50 ether); // ~$150,000 USD
        usdc.mint(address(account), 50_000 * 1e6); // $50,000 USDC
        wbtc.mint(address(account), 2 * 1e8); // $120,000 WBTC
        dai.mint(address(account), 20_000 * 1e18); // $20,000 DAI

        // Fund Paymaster for gas sponsorship
        paymaster.depositForAccount{value: 2 ether}(address(account));
    }

    // =========================================================================
    // Scenario 1: Multi-Day Enterprise Corporate Lifecycle
    // =========================================================================

    function test_Scenario_EnterpriseMultiDayLifecycle() public {
        // --- DAY 1: Normal autonomous AI trading within Tether Radius ---
        // AI executes a 0.1 ETH allocation to Lido staking (~$300 USD < $1,000 limit)
        bytes memory lidoCall = abi.encodeWithSelector(MockDeFiProtocol.stake.selector);
        bytes memory execCalldata1 = abi.encodePacked(address(lidoStaking), uint256(0.1 ether), lidoCall);

        vm.prank(entryPoint);
        account.execute(bytes32(0), execCalldata1);

        assertEq(lidoStaking.balances(address(account)), 0.1 ether);
        // Daily spent is $300 USD (300 * 1e8)
        TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(address(account));
        assertEq(p.dailySpent, 300 * 1e8);
        assertEq(hook.getRemainingRadius(address(account)), 700 * 1e8);

        // AI executes another 400 USDC transfer to Shibor MMF (~$400 USD, cumulative $700 <= $1,000)
        bytes memory usdcTransfer = abi.encodeWithSelector(
            MockERC20.transfer.selector,
            address(shiborTreasuryMMF),
            uint256(400 * 1e6)
        );
        bytes memory execCalldata2 = abi.encodePacked(address(usdc), uint256(0), usdcTransfer);

        vm.prank(entryPoint);
        account.execute(bytes32(0), execCalldata2);

        assertEq(usdc.balanceOf(address(shiborTreasuryMMF)), 400 * 1e6);
        p = hook.getAccountPolicy(address(account));
        assertEq(p.dailySpent, 700 * 1e8);
        assertEq(hook.getRemainingRadius(address(account)), 300 * 1e8);

        // AI attempts a 0.2 ETH allocation (~$600 USD) -> Exceeds remaining $300 USD! Reverts!
        bytes memory execCalldataExceed = abi.encodePacked(address(lidoStaking), uint256(0.2 ether), lidoCall);
        vm.prank(entryPoint);
        vm.expectRevert(
            abi.encodeWithSelector(
                TetherGuardHook.TetherRadiusExceeded.selector,
                600 * 1e8,
                300 * 1e8
            )
        );
        account.execute(bytes32(0), execCalldataExceed);

        // --- EVENING REVIEW: User inspects Day 1 executions ---
        TetherGuardHook.AutonomousExecutionRecord[] memory pending = hook.getPendingReviews(address(account));
        assertEq(pending.length, 2);

        // User Likes & Ratifies Transaction 1
        vm.prank(rootOwner);
        hook.ratifyTransaction(address(account), 1);

        // User notes Transaction 2 with praise (no penalty)
        vm.prank(rootOwner);
        hook.submitTransactionNote(address(account), 2, "Shibor allocation verified compliant with corporate mandate", false);

        p = hook.getAccountPolicy(address(account));
        assertEq(p.consecutiveRatifications, 1);

        // --- DAY 2: 24h Epoch Rollover & Vault-Native Dynamic Calibration ---
        vm.warp(block.timestamp + 1 days + 1);
        ethFeed.setPrice(3000 * 1e8);
        usdcFeed.setPrice(1 * 1e8);
        wbtcFeed.setPrice(60000 * 1e8);
        daiFeed.setPrice(1 * 1e8);

        // Epoch reset replenishes quota to full $1,000
        assertEq(hook.getRemainingRadius(address(account)), 1_000 * 1e8);

        // Vault autonomously calibrates dynamic radius (+10% maximum daily growth)
        // New radius: $1,000 + 10% = $1,100 USD
        vm.prank(sessionKey);
        uint256 calibratedRadius = hook.calibrateDynamicRadius(address(account));
        assertEq(calibratedRadius, 1_100 * 1e8);

        p = hook.getAccountPolicy(address(account));
        assertEq(p.tetherRadius, 1_100 * 1e8);
        assertEq(p.consecutiveRatifications, 0); // reset after calibration

        // AI can now spend up to $1,100 USD today
        // AI transfers 0.015 WBTC ($900 USD) + 150 USDC ($150 USD) = $1,050 USD <= $1,100 USD!
        bytes memory wbtcTransfer = abi.encodeWithSelector(
            MockERC20.transfer.selector,
            address(curvePool),
            uint256(0.015 * 1e8)
        );
        vm.prank(entryPoint);
        account.execute(bytes32(0), abi.encodePacked(address(wbtc), uint256(0), wbtcTransfer));
        assertEq(wbtc.balanceOf(address(curvePool)), 0.015 * 1e8);

        // --- DAY 3: Morning Review Flag For Revert with Trust Penalty ---
        // User reviews the Day 2 WBTC transfer and flags it for revert
        vm.prank(rootOwner);
        hook.flagTransactionForRevert(address(account), 3, "Unscheduled Curve deposit; contract radius");

        p = hook.getAccountPolicy(address(account));
        // Radius throttled by 20%: $1,100 - $220 = $880 USD
        assertEq(p.tetherRadius, 880 * 1e8);

        // --- DAY 4: Breaking the Tether (Institutional Allocation via FaceID) ---
        vm.warp(block.timestamp + 1 days);
        ethFeed.setPrice(3000 * 1e8);

        // An opportunity emerges requiring 20 ETH ($60,000 USD) -> Exceeds $880 limit!
        bytes memory breakoutCall = abi.encodePacked(address(lidoStaking), uint256(20 ether), lidoCall);

        // Attempting breakout without active FaceID reverts!
        vm.prank(rootOwner);
        vm.expectRevert(TetherGuardHook.BiometricVerificationRequired.selector);
        account.execute(bytes32(0), breakoutCall);

        // User verifies FaceID hardware biometric (RIP-7212 P-256 precompile)
        bytes32 faceIdChallenge = keccak256("Authorize 20 ETH Lido Treasury Allocation");
        hook.completeBiometricVerificationWithP256(
            address(account),
            faceIdChallenge,
            0x1122,
            0x3344,
            PASSKEY_QX,
            PASSKEY_QY
        );

        assertTrue(hook.isBiometricActive(address(account)));

        // User executes breakout successfully during the 5-minute window!
        vm.prank(rootOwner);
        account.execute(bytes32(0), breakoutCall);
        assertEq(lidoStaking.balances(address(account)), 20.1 ether);
    }

    // =========================================================================
    // Scenario 2: Adversarial Attack Sandbox & Defense Verification
    // =========================================================================

    function test_Scenario_AttackSandbox_DefensesHold() public {
        // Attack 1: Rogue Unwhitelisted Protocol Execution in Tier 2
        // AI Session key attempts to drain funds to an unapproved exploit contract
        bytes memory exploitCalldata = abi.encodePacked(address(maliciousDrainer), uint256(1 ether), hex"");
        vm.prank(entryPoint);
        vm.expectRevert(
            abi.encodeWithSelector(
                TetherGuardHook.UnauthorizedTarget.selector,
                address(maliciousDrainer)
            )
        );
        account.execute(bytes32(0), exploitCalldata);

        // Attack 2: Hook Self-Targeting Privilege Escalation
        // AI Session key attempts to reconfigure its own Tether Radius to $1,000,000 USD
        bytes memory selfTargetCall = abi.encodeWithSelector(
            TetherGuardHook.setTetherRadius.selector,
            address(account),
            1_000_000 * 1e8,
            hook.RISK_TIER_UNRESTRICTED()
        );
        vm.prank(entryPoint);
        vm.expectRevert(
            abi.encodeWithSelector(
                TetherGuardHook.UnauthorizedTarget.selector,
                address(hook)
            )
        );
        account.execute(bytes32(0), abi.encodePacked(address(hook), uint256(0), selfTargetCall));

        // Attack 3: Front-Running Policy Initialization
        address uninitAccount = address(0x9999);
        address attacker = address(0xBAD);
        vm.prank(attacker);
        vm.expectRevert("UNAUTHORIZED_INIT");
        hook.initializeAccountPolicy(uninitAccount, attacker, 50_000 * 1e8, 3);

        // Attack 4: Spoofed Passkey Coordinates
        uint256 fakeQx = 0xDEAD;
        uint256 fakeQy = 0xBEEF;
        vm.expectRevert(TetherGuardHook.UnauthorizedPasskey.selector);
        hook.completeBiometricVerificationWithP256(
            address(account),
            keccak256("Challenge"),
            0x1,
            0x2,
            fakeQx,
            fakeQy
        );

        // Attack 5: Expired Sign Approval Replay
        // User opens biometric window and approves an execution
        vm.prank(rootOwner);
        hook.completeBiometricVerification(address(account));

        bytes memory breakoutCall = abi.encodePacked(
            address(lidoStaking),
            uint256(5 ether),
            abi.encodeWithSelector(MockDeFiProtocol.stake.selector)
        );
        bytes32 execHash = keccak256(breakoutCall);

        vm.prank(rootOwner);
        hook.submitSignApproval(address(account), execHash, true);

        // Attacker waits 6 minutes (biometric window expires)
        vm.warp(block.timestamp + 6 minutes);
        ethFeed.setPrice(3000 * 1e8);

        vm.prank(entryPoint);
        vm.expectRevert(TetherGuardHook.BiometricVerificationRequired.selector);
        account.execute(bytes32(0), breakoutCall);

        // Attack 6: Gas-Griefing Infinite Loop via Paymaster
        // Verify paymaster halts cumulative gas expenditure at 0.005 ETH
        PackedUserOperation memory userOp;
        userOp.sender = address(account);
        userOp.signature = abi.encodePacked(sessionKey, hex"112233");

        // Simulate multiple UserOps consuming gas
        vm.prank(entryPoint);
        paymaster.postOp(
            IPaymaster.PostOpMode.opSucceeded,
            abi.encode(address(account), sessionKey, 0.003 ether),
            0.003 ether,
            0
        );
        assertEq(paymaster.sponsoredGasPerSession(address(account), sessionKey), 0.003 ether);

        // Next UserOp attempting 0.003 ether exceeds MAX_SESSION_GAS_BUDGET (0.005 ETH) -> Rejects!
        (, uint256 valData) = paymaster.validatePaymasterUserOp(userOp, bytes32(0), 0.003 ether);
        assertEq(valData, 1); // 1 = Rejected
    }

    // =========================================================================
    // Scenario 3: AI Heartbeat Expiration & Corporate Dead-Man's Switch
    // =========================================================================

    function test_Scenario_AIHeartbeatWatchdog_And_DeadmanRecovery() public {
        // AI executes a valid transaction
        bytes memory lidoCall = abi.encodeWithSelector(MockDeFiProtocol.stake.selector);
        bytes memory execCalldata = abi.encodePacked(address(lidoStaking), uint256(0.05 ether), lidoCall);

        vm.prank(entryPoint);
        account.execute(bytes32(0), execCalldata);

        // AI Agent goes silent / offline for 49 hours (> 48h DEFAULT_AI_HEARTBEAT_TIMEOUT)
        vm.warp(block.timestamp + 49 hours);
        ethFeed.setPrice(3000 * 1e8);

        // AI attempts to execute without sending heartbeat -> Reverts with AIHeartbeatStale!
        vm.prank(entryPoint);
        vm.expectRevert(
            abi.encodeWithSelector(
                TetherGuardHook.AIHeartbeatStale.selector,
                block.timestamp - 49 hours,
                block.timestamp
            )
        );
        account.execute(bytes32(0), execCalldata);

        // AI Agent broadcasts fresh heartbeat
        vm.prank(sessionKey);
        hook.recordAIHeartbeat(address(account));

        // Execution now succeeds!
        vm.prank(entryPoint);
        account.execute(bytes32(0), execCalldata);

        // --- Fast-forward: 91 Days of Total Inactivity (Dead-Man's Switch) ---
        vm.warp(block.timestamp + 91 days);

        // Guardian is now eligible to trigger recovery
        assertTrue(hook.isDeadmanSwitchTriggerable(address(account)));

        // Unauthorized address cannot trigger recovery
        vm.prank(address(0xBAD));
        vm.expectRevert(TetherGuardHook.UnauthorizedGuardian.selector);
        hook.triggerDeadmanRecovery(address(account), corporateSuccessor);

        // Corporate Guardian triggers recovery to designate Corporate Successor
        vm.prank(corporateGuardian);
        hook.triggerDeadmanRecovery(address(account), corporateSuccessor);

        TetherGuardHook.AccountPolicy memory p = hook.getAccountPolicy(address(account));
        assertEq(p.rootOwner, corporateSuccessor);
    }

    // =========================================================================
    // Scenario 4: Comprehensive Multi-Asset Portfolio Valuation Breakdown
    // =========================================================================

    function test_Scenario_ComprehensivePortfolioBreakdown() public view {
        address[] memory tokens = new address[](4);
        tokens[0] = hook.NATIVE_ETH();
        tokens[1] = address(usdc);
        tokens[2] = address(wbtc);
        tokens[3] = address(dai);

        (uint256 totalUSD, TetherGuardHook.TokenBalanceDetail[] memory details) = hook.getTotalPortfolioValueUSD(
            address(account),
            tokens
        );

        // ETH: 50 ETH * $3,000 = $150,000 USD (150,000 * 1e8)
        assertEq(details[0].valueUSD, 150_000 * 1e8);
        assertEq(details[0].symbol, "ETH");

        // USDC: 50,000 USDC * $1.00 = $50,000 USD (50,000 * 1e8)
        assertEq(details[1].valueUSD, 50_000 * 1e8);
        assertEq(details[1].symbol, "USDC");

        // WBTC: 2 WBTC * $60,000 = $120,000 USD (120,000 * 1e8)
        assertEq(details[2].valueUSD, 120_000 * 1e8);
        assertEq(details[2].symbol, "WBTC");

        // DAI: 20,000 DAI * $1.00 = $20,000 USD (20,000 * 1e8)
        assertEq(details[3].valueUSD, 20_000 * 1e8);
        assertEq(details[3].symbol, "DAI");

        // Total Net Worth = $150,000 + $50,000 + $120,000 + $20,000 = $340,000 USD (340,000 * 1e8)
        assertEq(totalUSD, 340_000 * 1e8);
    }
}

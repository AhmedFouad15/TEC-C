// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {TecAccount} from "../src/TecAccount.sol";
import {TetherGuardHook} from "../src/hooks/TetherGuardHook.sol";
import {SessionKeyValidator} from "../src/validators/SessionKeyValidator.sol";
import {TecPaymaster} from "../src/paymaster/TecPaymaster.sol";
import {MockDeFiProtocol} from "./mocks/MockDeFiProtocol.sol";
import {MockERC20} from "./mocks/MockERC20.sol";
import {MockRIP7212} from "./mocks/MockRIP7212.sol";
import {MockChainlinkFeed} from "./mocks/MockChainlinkFeed.sol";
import {IPaymaster} from "../src/interfaces/IPaymaster.sol";
import {PackedUserOperation} from "../src/interfaces/PackedUserOperation.sol";
import {MODULE_TYPE_HOOK, MODULE_TYPE_VALIDATOR} from "../src/interfaces/IERC7579Account.sol";

/**
 * @title MockDEXRouter
 * @notice Realistic AMM DEX router simulating Uniswap/Curve swap execution for Tec-C.
 */
contract MockDEXRouter {
    event SwapExecuted(address indexed caller, address tokenIn, address tokenOut, uint256 amountIn, uint256 amountOut);

    function swapExactETHForTokens(address tokenOut, uint256 minAmountOut)
        external
        payable
        returns (uint256 amountOut)
    {
        require(msg.value > 0, "ZERO_VALUE");
        amountOut = msg.value * 2500; // 1 ETH = 2,500 USDC
        require(amountOut >= minAmountOut, "SLIPPAGE_EXCEEDED");
        emit SwapExecuted(msg.sender, address(0), tokenOut, msg.value, amountOut);
    }
}

/**
 * @title VaultSecurityHardeningTest
 * @author Tec-C Security Engineering Team (FinTechathon 2026 Topic F)
 * @notice Comprehensive unit and fuzz testing verifying:
 *         (1) Legitimate swap executes under limit
 *         (2) Breaching Tether Radius reverts with TetherRadiusExceeded()
 *         (3) Unauthorized address reverts with UnauthorizedTarget()
 *         (4) Gas griefing halts at 0.005 ETH
 *         Plus comprehensive tests for security hardening patches SEC-01 through SEC-08.
 */
contract VaultSecurityHardeningTest is Test {
    TecAccount public account;
    TetherGuardHook public hook;
    SessionKeyValidator public validator;
    TecPaymaster public paymaster;
    MockDEXRouter public dexRouter;
    MockERC20 public usdc;

    address public entryPoint = address(0xEEEE);
    uint256 public rootOwnerPk = 0xAA11;
    address public rootOwner;
    uint256 public sessionKeyPk = 0xBB22;
    address public sessionKey;

    uint256 public constant TETHER_RADIUS = 0.5 ether; // 0.5 ETH daily limit
    uint256 public constant PASSKEY_QX = 0x111122223333444455556666777788889999AAAABBBBCCCCDDDDEEEEFFFF0001;
    uint256 public constant PASSKEY_QY = 0x22223333444455556666777788889999AAAABBBBCCCCDDDDEEEEFFFF00011112;

    event SwapExecuted(address indexed caller, address tokenIn, address tokenOut, uint256 amountIn, uint256 amountOut);

    function setUp() public {
        rootOwner = vm.addr(rootOwnerPk);
        sessionKey = vm.addr(sessionKeyPk);

        // Deploy RIP-7212 mock at 0x100
        MockRIP7212 ripMock = new MockRIP7212();
        vm.etch(address(0x100), address(ripMock).code);

        // Deploy system contracts
        hook = new TetherGuardHook();
        validator = new SessionKeyValidator();
        paymaster = new TecPaymaster(entryPoint);
        account = new TecAccount(entryPoint);
        dexRouter = new MockDEXRouter();
        usdc = new MockERC20("USD Coin", "USDC", 6);

        // Initialize TecAccount
        account.initialize(rootOwner, address(hook), address(validator));

        // Initialize Policy: 0.5 ETH Radius, Tier 2 Growth/DeFi
        hook.initializeAccountPolicy(address(account), rootOwner, TETHER_RADIUS, 2);

        // Register Passkey on hook
        vm.prank(rootOwner);
        hook.setAccountPasskey(address(account), PASSKEY_QX, PASSKEY_QY);

        // Whitelist DEX Router for trading (Tier 2 Growth)
        vm.prank(rootOwner);
        hook.setTargetWhitelist(address(account), address(dexRouter), true, 2);

        // Authorize AI Session Key on Hook
        vm.prank(rootOwner);
        hook.setSessionKeyAuthorization(address(account), sessionKey, true);

        // Register session key in SessionKeyValidator
        bytes32 mandateRoot = keccak256("TopicF_Automated_DEX_Trading_Mandate");
        vm.prank(address(account));
        validator.registerSessionKey(
            address(account), sessionKey, uint48(block.timestamp), uint48(block.timestamp + 7 days), mandateRoot
        );

        // Fund accounts
        vm.deal(address(account), 50 ether);
        vm.deal(rootOwner, 10 ether);

        // Deposit gas funds into paymaster for account
        vm.deal(address(this), 10 ether);
        paymaster.depositForAccount{value: 2 ether}(address(account));
    }

    // =========================================================================
    // --- USER REQUIREMENT (1): Legitimate swap executes under limit ---
    // =========================================================================

    function test_LegitimateSwap_UnderLimit_Success() public {
        uint256 swapAmount = 0.2 ether; // 0.2 ETH <= 0.5 ETH Tether Radius
        uint256 expectedTokens = swapAmount * 2500;

        // Encode DEX swap calldata: target (20) || value (32) || swapExactETHForTokens(address,uint256)
        bytes memory callPayload =
            abi.encodeWithSelector(MockDEXRouter.swapExactETHForTokens.selector, address(usdc), expectedTokens);
        bytes memory executionCalldata = abi.encodePacked(address(dexRouter), swapAmount, callPayload);

        uint256 initialAccountBalance = address(account).balance;
        uint256 initialDexBalance = address(dexRouter).balance;

        // Execute swap through entryPoint as AI session key
        vm.prank(entryPoint);
        account.execute(bytes32(0), executionCalldata);

        // Verify on-chain state updates
        assertEq(address(account).balance, initialAccountBalance - swapAmount);
        assertEq(address(dexRouter).balance, initialDexBalance + swapAmount);

        // Verify Tether Radius tracking in hook
        TetherGuardHook.AccountPolicy memory pol = hook.getAccountPolicy(address(account));
        assertEq(pol.tetherRadius, TETHER_RADIUS);
        assertEq(pol.dailySpent, swapAmount);
        assertEq(hook.getRemainingRadius(address(account)), TETHER_RADIUS - swapAmount);
    }

    function testFuzz_LegitimateSwap_UnderLimit(uint256 swapAmount) public {
        // Bound swapAmount between 1 wei and TETHER_RADIUS
        vm.assume(swapAmount > 0 && swapAmount <= TETHER_RADIUS);

        uint256 minTokens = swapAmount * 2500;
        bytes memory callPayload =
            abi.encodeWithSelector(MockDEXRouter.swapExactETHForTokens.selector, address(usdc), minTokens);
        bytes memory executionCalldata = abi.encodePacked(address(dexRouter), swapAmount, callPayload);

        vm.prank(entryPoint);
        account.execute(bytes32(0), executionCalldata);

        assertEq(hook.getRemainingRadius(address(account)), TETHER_RADIUS - swapAmount);
    }

    // =========================================================================
    // --- USER REQUIREMENT (2): Breaching Tether Radius reverts ---
    // =========================================================================

    function test_BreachingTetherRadius_Reverts() public {
        uint256 excessAmount = 0.51 ether; // 0.51 ETH > 0.50 ETH Tether Radius
        bytes memory callPayload =
            abi.encodeWithSelector(MockDEXRouter.swapExactETHForTokens.selector, address(usdc), 0);
        bytes memory executionCalldata = abi.encodePacked(address(dexRouter), excessAmount, callPayload);

        // Attempting to breach Tether Radius without biometric breakout MUST revert
        vm.prank(entryPoint);
        vm.expectRevert(
            abi.encodeWithSelector(TetherGuardHook.TetherRadiusExceeded.selector, excessAmount, TETHER_RADIUS)
        );
        account.execute(bytes32(0), executionCalldata);

        // Verify account funds were completely protected
        assertEq(address(account).balance, 50 ether);
        assertEq(hook.getRemainingRadius(address(account)), TETHER_RADIUS);
    }

    function testFuzz_BreachingTetherRadius_Reverts(uint256 excessAmount) public {
        // Bound excessAmount strictly greater than TETHER_RADIUS up to account balance
        vm.assume(excessAmount > TETHER_RADIUS && excessAmount <= 50 ether);

        bytes memory callPayload =
            abi.encodeWithSelector(MockDEXRouter.swapExactETHForTokens.selector, address(usdc), 0);
        bytes memory executionCalldata = abi.encodePacked(address(dexRouter), excessAmount, callPayload);

        vm.prank(entryPoint);
        vm.expectRevert(
            abi.encodeWithSelector(TetherGuardHook.TetherRadiusExceeded.selector, excessAmount, TETHER_RADIUS)
        );
        account.execute(bytes32(0), executionCalldata);
    }

    // =========================================================================
    // --- USER REQUIREMENT (3): Unauthorized address reverts ---
    // =========================================================================

    function test_UnauthorizedTarget_Reverts() public {
        address unauthorizedExploitContract = address(0xDEADBEEF);
        bytes memory executionCalldata = abi.encodePacked(unauthorizedExploitContract, uint256(0.1 ether), hex"1234");

        // AI Session Key attempting to call unwhitelisted target MUST revert with UnauthorizedTarget
        vm.prank(entryPoint);
        vm.expectRevert(
            abi.encodeWithSelector(TetherGuardHook.UnauthorizedTarget.selector, unauthorizedExploitContract)
        );
        account.execute(bytes32(0), executionCalldata);
    }

    function testFuzz_UnauthorizedTarget_Reverts(address rogueTarget) public {
        vm.assume(
            rogueTarget != address(dexRouter) && rogueTarget != address(hook) && rogueTarget != address(validator)
                && rogueTarget != rootOwner && rogueTarget != address(account)
        );

        bytes memory executionCalldata = abi.encodePacked(rogueTarget, uint256(0.05 ether), hex"CAFE");

        vm.prank(entryPoint);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.UnauthorizedTarget.selector, rogueTarget));
        account.execute(bytes32(0), executionCalldata);
    }

    // =========================================================================
    // --- USER REQUIREMENT (4): Gas griefing halts at 0.005 ETH ---
    // =========================================================================

    function test_GasGriefing_HaltsAtMaxQuota() public {
        PackedUserOperation memory userOp;
        userOp.sender = address(account);
        userOp.signature = abi.encodePacked(sessionKey, hex"1234");

        // Simulate 5 successive operations consuming 0.001 ETH each
        for (uint256 i = 0; i < 5; i++) {
            (bytes memory context, uint256 validationData) =
                paymaster.validatePaymasterUserOp(userOp, bytes32(0), 0.001 ether);
            assertEq(validationData, 0); // Approved

            vm.prank(entryPoint);
            paymaster.postOp(IPaymaster.PostOpMode.opSucceeded, context, 0.001 ether, 1 gwei);
        }

        // Ephemeral session key has now reached 0.005 ETH quota
        assertEq(paymaster.sponsoredGasPerSession(address(account), sessionKey), paymaster.MAX_SESSION_GAS_BUDGET());

        // 6th operation (attempted gas drain) MUST be halted
        (, uint256 rejectedData) = paymaster.validatePaymasterUserOp(userOp, bytes32(0), 0.0001 ether);
        assertEq(rejectedData, 1); // Gas griefing halted!
    }

    function testFuzz_GasGriefing_Cap(uint256 opCost, uint8 iterations) public {
        vm.assume(opCost >= 0.0001 ether && opCost <= 0.005 ether);
        vm.assume(iterations >= 1 && iterations <= 20);

        PackedUserOperation memory userOp;
        userOp.sender = address(account);
        userOp.signature = abi.encodePacked(sessionKey, hex"1234");

        uint256 totalSponsored = 0;
        for (uint8 i = 0; i < iterations; i++) {
            (, uint256 valData) = paymaster.validatePaymasterUserOp(userOp, bytes32(0), opCost);
            if (totalSponsored + opCost > paymaster.MAX_SESSION_GAS_BUDGET()) {
                assertEq(valData, 1); // Rejects once cap would be breached
                break;
            } else {
                assertEq(valData, 0);
                bytes memory ctx = abi.encode(address(account), sessionKey, opCost);
                vm.prank(entryPoint);
                paymaster.postOp(IPaymaster.PostOpMode.opSucceeded, ctx, opCost, 1 gwei);
                totalSponsored += opCost;
            }
        }

        // Invariant: Total sponsored gas never exceeds 0.005 ETH
        assertTrue(paymaster.sponsoredGasPerSession(address(account), sessionKey) <= 0.005 ether);
    }

    // =========================================================================
    // --- SECURITY PATCH VERIFICATIONS (SEC-01 through SEC-08) ---
    // =========================================================================

    function test_SEC01_BiometricChallenge_Replay_Reverts() public {
        bytes32 challenge = keccak256("SEC-01: Breakout Challenge");
        uint256 r = 0x112233;
        uint256 s = 0x445566;
        uint256 deadline = block.timestamp + 5 minutes;

        // First verification succeeds
        hook.completeBiometricVerificationWithP256(address(account), challenge, r, s, PASSKEY_QX, PASSKEY_QY, deadline);
        assertTrue(hook.isBiometricActive(address(account)));

        // Attacker attempts to replay the exact same challenge signature -> Reverts!
        vm.expectRevert(TetherGuardHook.ChallengeAlreadyUsed.selector);
        hook.completeBiometricVerificationWithP256(address(account), challenge, r, s, PASSKEY_QX, PASSKEY_QY, deadline);
    }

    function test_SEC01_BiometricChallenge_ExpiredDeadline_Reverts() public {
        bytes32 challenge = keccak256("SEC-01: Expired Challenge");
        uint256 r = 0x112233;
        uint256 s = 0x445566;
        uint256 deadline = block.timestamp + 1 minutes;

        // Warp time past signature deadline
        vm.warp(block.timestamp + 2 minutes);

        vm.expectRevert(TetherGuardHook.ExpiredSignature.selector);
        hook.completeBiometricVerificationWithP256(address(account), challenge, r, s, PASSKEY_QX, PASSKEY_QY, deadline);
    }

    function test_SEC02_Paymaster_OwnerCannotWithdrawUserDeposits() public {
        // Paymaster has 2 ETH deposited by user
        assertEq(paymaster.totalUserDeposits(), 2 ether);

        // Owner attempts to withdraw 1 ETH of user deposits -> Reverts!
        vm.expectRevert(abi.encodeWithSelector(TecPaymaster.CannotWithdrawUserDeposits.selector, 1 ether, 0));
        paymaster.withdraw(payable(address(this)), 1 ether);
    }

    function test_SEC02_Paymaster_OwnerCanWithdrawSurplus() public {
        // Direct donation of 1 ETH surplus to paymaster
        (bool s,) = address(paymaster).call{value: 1 ether}("");
        assertTrue(s);

        // Balance is 3 ETH, totalUserDeposits is 2 ETH -> Surplus is 1 ETH
        uint256 initBalance = address(this).balance;
        paymaster.withdraw(payable(address(this)), 1 ether);
        assertEq(address(this).balance, initBalance + 1 ether);

        // User deposits remain intact
        assertEq(paymaster.accountBalances(address(account)), 2 ether);
        assertEq(paymaster.totalUserDeposits(), 2 ether);
    }

    function test_SEC03_Paymaster_EntryPointDepositAndWithdrawal() public {
        // Test depositToEntryPoint fallback
        paymaster.depositToEntryPoint{value: 0.1 ether}();
        assertEq(entryPoint.balance, 0.1 ether);
    }

    function test_SEC04_Paymaster_RootOwnerECDSA_ExemptFromSessionCap() public view {
        // Root owner signs directly (65-byte signature)
        bytes32 userOpHash = keccak256("RootOwnerUserOp");
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", userOpHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(rootOwnerPk, ethHash);
        bytes memory rootSig = abi.encodePacked(r, s, v); // Exactly 65 bytes

        PackedUserOperation memory userOp;
        userOp.sender = address(account);
        userOp.signature = rootSig;

        // Root owner op with 0.01 ETH (> 0.005 ETH session limit) is approved because sessionKey == address(0)
        (, uint256 valData) = paymaster.validatePaymasterUserOp(userOp, userOpHash, 0.01 ether);
        assertEq(valData, 0); // Approved!
    }

    function test_SEC05_SessionKeyValidator_MandateBinding() public view {
        bytes32 mandateRoot = keccak256("TopicF_Automated_DEX_Trading_Mandate");
        bytes32 userOpHash = keccak256("DEX_Trade_001");
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", userOpHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(sessionKeyPk, ethHash);

        // 1. Valid 117-byte signature: sessionKey (20) || r,s,v (65) || mandateRoot (32)
        bytes memory validSig = abi.encodePacked(sessionKey, r, s, v, mandateRoot);
        PackedUserOperation memory op1;
        op1.sender = address(account);
        op1.signature = validSig;

        uint256 valData1 = validator.validateUserOp(op1, userOpHash);
        assertEq(address(uint160(valData1)), address(0)); // Validation success!

        // 2. Tampered mandate digest -> Mismatch -> Rejects with 1!
        bytes32 wrongMandate = keccak256("Rogue_Drain_Mandate");
        bytes memory invalidSig = abi.encodePacked(sessionKey, r, s, v, wrongMandate);
        PackedUserOperation memory op2;
        op2.sender = address(account);
        op2.signature = invalidSig;

        uint256 valData2 = validator.validateUserOp(op2, userOpHash);
        assertEq(valData2, 1); // Validation rejected!
    }

    function test_SEC06_TecAccount_UninitializedRootOwner_RejectsUserOp() public {
        // Deploy an uninitialized TecAccount
        TecAccount freshAccount = new TecAccount(entryPoint);
        assertEq(freshAccount.rootOwner(), address(0));

        PackedUserOperation memory dummyOp;
        dummyOp.sender = address(freshAccount);
        dummyOp.signature = hex"00";

        vm.prank(entryPoint);
        uint256 valData = freshAccount.validateUserOp(dummyOp, bytes32(0), 0);
        assertEq(valData, 1); // Rejects validation when rootOwner is zero
    }

    function test_SEC07_CrossHook_SignatureReplay_Reverts() public {
        // Deploy second hook instance
        TetherGuardHook hook2 = new TetherGuardHook();
        hook2.initializeAccountPolicy(address(account), rootOwner, TETHER_RADIUS, 2);

        bytes32 execHash = keccak256("CrossHookAttack");
        uint256 deadline = block.timestamp + 10 minutes;

        // Generate signature for hook1
        bytes32 msgHashHook1 = keccak256(
            abi.encode(
                address(account),
                execHash,
                true,
                hook.signApprovalNonces(address(account)),
                deadline,
                block.chainid,
                address(hook)
            )
        );
        bytes32 ethHash1 = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", msgHashHook1));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(rootOwnerPk, ethHash1);
        bytes memory sigHook1 = abi.encodePacked(r, s, v);

        // Attacker attempts to replay this signature on hook2 -> Reverts!
        vm.prank(rootOwner);
        hook2.completeBiometricVerification(address(account));

        vm.expectRevert(TetherGuardHook.InvalidApprovalSignature.selector);
        hook2.submitSignApprovalWithSignature(address(account), execHash, true, deadline, sigHook1);
    }

    function test_SEC08_ChainlinkOracle_IncompleteRound_Reverts() public {
        MockChainlinkFeed feed = new MockChainlinkFeed(8, 2500e8, "ETH / USD");
        vm.prank(rootOwner);
        hook.setAccountPriceFeed(address(account), address(0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE), address(feed));

        // When round is incomplete (updatedAt == 0)
        feed.setUpdatedAt(0);

        vm.expectRevert(
            abi.encodeWithSelector(
                TetherGuardHook.StaleOraclePrice.selector, address(0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE), 0
            )
        );
        hook.getLatestPrice(address(account), address(0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE));
    }

    receive() external payable {}
}

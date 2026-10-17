// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {TetherGuardHook} from "../src/hooks/TetherGuardHook.sol";
import {MockChainlinkFeed} from "./mocks/MockChainlinkFeed.sol";
import {MockERC20} from "./mocks/MockERC20.sol";
import {IERC20} from "../src/interfaces/IERC20.sol";

/**
 * @title CrossChainTetherTest
 * @notice Validates multi-chain vault deployment and cross-chain tether radius synchronization
 *         across Ethereum Mainnet, Arbitrum One, and FISCO BCOS consortium network.
 * @dev Enforces the cross-chain rule: if $500 is spent on Ethereum and the daily limit is $500,
 *      the vault locks across all 3 chains (Ethereum, Arbitrum, FISCO BCOS).
 */
contract CrossChainTetherTest is Test {
    // Hooks deployed on each target chain
    TetherGuardHook public ethHook;
    TetherGuardHook public arbHook;
    TetherGuardHook public fiscoHook;

    // Tokens and Price Feeds
    MockERC20 public usdc;
    MockChainlinkFeed public usdcFeed;
    MockChainlinkFeed public ethFeed;

    // Identities
    uint256 public rootOwnerPk = 0xA11CE;
    address public rootOwner;
    address public tecAccount = address(0xBB22);
    address public sessionKey = address(0xCC33);
    address public relayer = address(0xEE55);
    address public recipient = address(0xDD44);

    // Institutional Daily Limit: $500 USD (8 decimal precision)
    uint256 public constant TETHER_RADIUS_USD = 500 * 1e8; // $500.00
    uint8 public constant TIER_BALANCED = 2;

    // Chain IDs
    uint256 public constant CHAIN_ETHEREUM = 1;
    uint256 public constant CHAIN_ARBITRUM = 42161;
    uint256 public constant CHAIN_FISCO = 2026;

    function setUp() public {
        rootOwner = vm.addr(rootOwnerPk);

        // 1. Deploy hooks for each chain
        ethHook = new TetherGuardHook();
        arbHook = new TetherGuardHook();
        fiscoHook = new TetherGuardHook();

        // 2. Deploy common token and feeds ($1.00 USDC, $3000 ETH)
        usdc = new MockERC20("USD Coin", "USDC", 6);
        usdcFeed = new MockChainlinkFeed(8, 1 * 1e8, "USDC / USD");
        ethFeed = new MockChainlinkFeed(8, 3000 * 1e8, "ETH / USD");

        // 3. Configure each chain's hook
        _configureHook(ethHook);
        _configureHook(arbHook);
        _configureHook(fiscoHook);

        // 4. Fund tecAccount with USDC
        usdc.mint(tecAccount, 100_000 * 1e6); // 100,000 USDC
    }

    function _configureHook(TetherGuardHook targetHook) internal {
        // Price feeds
        targetHook.setGlobalPriceFeed(address(usdc), address(usdcFeed));
        targetHook.setGlobalPriceFeed(targetHook.NATIVE_ETH(), address(ethFeed));

        // Account policy with $500 daily radius
        targetHook.initializeAccountPolicy(tecAccount, rootOwner, TETHER_RADIUS_USD, TIER_BALANCED);

        // Whitelist recipient as Tier 2
        vm.prank(rootOwner);
        targetHook.setTargetWhitelist(tecAccount, recipient, true, TIER_BALANCED);

        // Whitelist USDC token transfer target
        vm.prank(rootOwner);
        targetHook.setTargetWhitelist(tecAccount, address(usdc), true, TIER_BALANCED);

        // Authorize AI Session Key
        vm.prank(rootOwner);
        targetHook.setSessionKeyAuthorization(tecAccount, sessionKey, true);

        // Authorize cross-chain relayer
        targetHook.setCrossChainRelayer(relayer, true);
    }

    /**
     * @notice Verifies initial state across Ethereum, Arbitrum, and FISCO BCOS:
     *         each has exactly $500 remaining allowance.
     */
    function test_InitialCrossChainState_AllChainsHave500Radius() public view {
        assertEq(ethHook.getRemainingRadius(tecAccount), TETHER_RADIUS_USD);
        assertEq(arbHook.getRemainingRadius(tecAccount), TETHER_RADIUS_USD);
        assertEq(fiscoHook.getRemainingRadius(tecAccount), TETHER_RADIUS_USD);
    }

    /**
     * @notice CORE REQUIREMENT TEST:
     *         If the Brain spends $500 on Ethereum and the daily limit is $500,
     *         it CANNOT transact on any of the 3 (Ethereum, Arbitrum, FISCO BCOS).
     */
    function test_CrossChain_FullSpendOnEthereum_LocksAllThreeChains() public {
        uint256 epoch = block.timestamp / 1 days;

        // Spend $500 USD (500 USDC = 500 * 1e6) on Ethereum
        bytes memory execData = abi.encodePacked(
            address(usdc),
            uint256(0),
            abi.encodeWithSelector(IERC20.transfer.selector, recipient, uint256(500 * 1e6))
        );

        vm.prank(tecAccount);
        bytes memory hookData = ethHook.preCheck(sessionKey, 0, execData);
        vm.prank(tecAccount);
        ethHook.postCheck(hookData);

        // Ethereum hook remaining radius is now 0
        assertEq(ethHook.getRemainingRadius(tecAccount), 0);

        // Ethereum attempt to spend $1 more reverts immediately
        bytes memory oneDollarExec = abi.encodePacked(
            address(usdc),
            uint256(0),
            abi.encodeWithSelector(IERC20.transfer.selector, recipient, uint256(1 * 1e6))
        );
        vm.prank(tecAccount);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.TetherRadiusExceeded.selector, 1 * 1e8, 0));
        ethHook.preCheck(sessionKey, 0, oneDollarExec);

        // Relayer syncs the $500 spend to Arbitrum and FISCO BCOS
        vm.prank(relayer);
        arbHook.syncCrossChainSpend(tecAccount, CHAIN_ETHEREUM, TETHER_RADIUS_USD, epoch);

        vm.prank(relayer);
        fiscoHook.syncCrossChainSpend(tecAccount, CHAIN_ETHEREUM, TETHER_RADIUS_USD, epoch);

        // Verify remaining radius is 0 on Arbitrum and FISCO BCOS
        assertEq(arbHook.getRemainingRadius(tecAccount), 0);
        assertEq(fiscoHook.getRemainingRadius(tecAccount), 0);

        // Attempt transaction on Arbitrum -> REVERTS!
        vm.prank(tecAccount);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.TetherRadiusExceeded.selector, 1 * 1e8, 0));
        arbHook.preCheck(sessionKey, 0, oneDollarExec);

        // Attempt transaction on FISCO BCOS -> REVERTS!
        vm.prank(tecAccount);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.TetherRadiusExceeded.selector, 1 * 1e8, 0));
        fiscoHook.preCheck(sessionKey, 0, oneDollarExec);
    }

    /**
     * @notice Multi-Chain Velocity Aggregation:
     *         $200 spent on Ethereum + $300 spent on Arbitrum = $500 total.
     *         Locks FISCO BCOS and all chains from further spending.
     */
    function test_CrossChain_PartialSpendsAggregate_LocksRemainingAllowance() public {
        uint256 epoch = block.timestamp / 1 days;

        // 1. Spend $200 on Ethereum
        bytes memory spend200 = abi.encodePacked(
            address(usdc),
            uint256(0),
            abi.encodeWithSelector(IERC20.transfer.selector, recipient, uint256(200 * 1e6))
        );
        vm.prank(tecAccount);
        bytes memory hookData1 = ethHook.preCheck(sessionKey, 0, spend200);
        vm.prank(tecAccount);
        ethHook.postCheck(hookData1);

        assertEq(ethHook.getRemainingRadius(tecAccount), 300 * 1e8);

        // Sync $200 spend to Arbitrum & FISCO BCOS
        vm.prank(relayer);
        arbHook.syncCrossChainSpend(tecAccount, CHAIN_ETHEREUM, 200 * 1e8, epoch);
        vm.prank(relayer);
        fiscoHook.syncCrossChainSpend(tecAccount, CHAIN_ETHEREUM, 200 * 1e8, epoch);

        assertEq(arbHook.getRemainingRadius(tecAccount), 300 * 1e8);
        assertEq(fiscoHook.getRemainingRadius(tecAccount), 300 * 1e8);

        // 2. Spend remaining $300 on Arbitrum
        bytes memory spend300 = abi.encodePacked(
            address(usdc),
            uint256(0),
            abi.encodeWithSelector(IERC20.transfer.selector, recipient, uint256(300 * 1e6))
        );
        vm.prank(tecAccount);
        bytes memory hookData2 = arbHook.preCheck(sessionKey, 0, spend300);
        vm.prank(tecAccount);
        arbHook.postCheck(hookData2);

        assertEq(arbHook.getRemainingRadius(tecAccount), 0);

        // Sync $300 spend from Arbitrum to Ethereum & FISCO BCOS
        vm.prank(relayer);
        ethHook.syncCrossChainSpend(tecAccount, CHAIN_ARBITRUM, 300 * 1e8, epoch);
        vm.prank(relayer);
        fiscoHook.syncCrossChainSpend(tecAccount, CHAIN_ARBITRUM, 300 * 1e8, epoch);

        // All 3 chains are now fully exhausted ($0 remaining)
        assertEq(ethHook.getRemainingRadius(tecAccount), 0);
        assertEq(arbHook.getRemainingRadius(tecAccount), 0);
        assertEq(fiscoHook.getRemainingRadius(tecAccount), 0);

        // FISCO BCOS cannot execute even $1
        bytes memory spend1 = abi.encodePacked(
            address(usdc),
            uint256(0),
            abi.encodeWithSelector(IERC20.transfer.selector, recipient, uint256(1 * 1e6))
        );
        vm.prank(tecAccount);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.TetherRadiusExceeded.selector, 1 * 1e8, 0));
        fiscoHook.preCheck(sessionKey, 0, spend1);
    }

    /**
     * @notice Verifies cryptographic spend proof relay with ECDSA signature and replay protection.
     */
    function test_CrossChain_SignedSpendProof_SyncsAndReplayProtected() public {
        uint256 epoch = block.timestamp / 1 days;
        uint256 nonce = 101;
        uint256 deadline = block.timestamp + 1 hours;

        TetherGuardHook.CrossChainSpendProof memory proof = TetherGuardHook.CrossChainSpendProof({
            account: tecAccount,
            sourceChainId: CHAIN_ETHEREUM,
            amountUSD: 500 * 1e8,
            epoch: epoch,
            nonce: nonce,
            deadline: deadline
        });

        // Compute hash matching arbHook's chainid and address
        bytes32 messageHash = keccak256(
            abi.encode(
                proof.account,
                proof.sourceChainId,
                proof.amountUSD,
                proof.epoch,
                proof.nonce,
                proof.deadline,
                block.chainid,
                address(arbHook)
            )
        );
        bytes32 ethSigned = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(rootOwnerPk, ethSigned);
        bytes memory sig = abi.encodePacked(r, s, v);

        // Submit to Arbitrum hook via untrusted caller
        arbHook.syncCrossChainSpendWithSignature(proof, sig);

        // Arbitrum is now locked
        assertEq(arbHook.getRemainingRadius(tecAccount), 0);

        // Replay of same nonce reverts
        vm.expectRevert(bytes("NONCE_ALREADY_USED"));
        arbHook.syncCrossChainSpendWithSignature(proof, sig);
    }

    /**
     * @notice Verifies that after 24h epoch rollover, the daily spending limit is replenished on all chains.
     */
    function test_CrossChain_EpochRollover_ReplenishesQuotaOnAllChains() public {
        uint256 epoch = block.timestamp / 1 days;

        // Exhaust limit on Ethereum and sync to all chains
        vm.prank(relayer);
        ethHook.syncCrossChainSpend(tecAccount, CHAIN_FISCO, 500 * 1e8, epoch);
        vm.prank(relayer);
        arbHook.syncCrossChainSpend(tecAccount, CHAIN_FISCO, 500 * 1e8, epoch);
        vm.prank(relayer);
        fiscoHook.syncCrossChainSpend(tecAccount, CHAIN_FISCO, 500 * 1e8, epoch);

        assertEq(ethHook.getRemainingRadius(tecAccount), 0);
        assertEq(arbHook.getRemainingRadius(tecAccount), 0);
        assertEq(fiscoHook.getRemainingRadius(tecAccount), 0);

        // Advance time by 24 hours + 1 second
        vm.warp(block.timestamp + 1 days + 1);

        // Daily radius is automatically replenished on all 3 chains!
        assertEq(ethHook.getRemainingRadius(tecAccount), TETHER_RADIUS_USD);
        assertEq(arbHook.getRemainingRadius(tecAccount), TETHER_RADIUS_USD);
        assertEq(fiscoHook.getRemainingRadius(tecAccount), TETHER_RADIUS_USD);
    }

    /**
     * @notice Verifies breakout execution with biometric verification and sign approval
     *         even when the cross-chain tether radius is exhausted.
     */
    function test_CrossChain_BreakoutWithBiometrics_SucceedsWhenLocked() public {
        uint256 epoch = block.timestamp / 1 days;

        // Lock Arbitrum via remote spend
        vm.prank(relayer);
        arbHook.syncCrossChainSpend(tecAccount, CHAIN_ETHEREUM, 500 * 1e8, epoch);
        assertEq(arbHook.getRemainingRadius(tecAccount), 0);

        bytes memory breakoutTx = abi.encodePacked(
            address(usdc),
            uint256(0),
            abi.encodeWithSelector(IERC20.transfer.selector, recipient, uint256(100 * 1e6))
        );
        bytes32 execHash = keccak256(breakoutTx);

        // 1. Without biometrics -> Reverts
        vm.prank(tecAccount);
        vm.expectRevert(abi.encodeWithSelector(TetherGuardHook.TetherRadiusExceeded.selector, 100 * 1e8, 0));
        arbHook.preCheck(sessionKey, 0, breakoutTx);

        // 2. User completes Biometric Verification on Arbitrum
        vm.prank(rootOwner);
        arbHook.completeBiometricVerification(tecAccount);
        assertTrue(arbHook.isBiometricActive(tecAccount));

        // 3. User submits Sign Approval
        vm.prank(rootOwner);
        arbHook.submitSignApproval(tecAccount, execHash, true);

        // 4. Brain executes breakout transaction -> SUCCEEDS!
        vm.prank(tecAccount);
        bytes memory hookData = arbHook.preCheck(sessionKey, 0, breakoutTx);
        vm.prank(tecAccount);
        arbHook.postCheck(hookData);

        assertEq(arbHook.totalAuditedExecutions(), 1);
    }
}

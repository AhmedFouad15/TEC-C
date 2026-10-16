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
import {MODULE_TYPE_HOOK, MODULE_TYPE_VALIDATOR, MODULE_TYPE_EXECUTOR} from "../src/interfaces/IERC7579Account.sol";

/**
 * @title VaultGasBenchmarkTest
 * @author Tec-C Core Engineering Team (FinTechathon 2026 Topic F)
 * @notice Measures empirical EVM execution gas units and transaction fees (ETH @ 20 gwei, USD @ $2,500/ETH)
 *         for every method that can be used across the Tec-C Vault architecture.
 */
contract VaultGasBenchmarkTest is Test {
    SessionKeyValidator public validator;
    TecPaymaster public paymaster;
    MockDeFiProtocol public lidoStaking;
    MockERC20 public usdc;
    MockChainlinkFeed public ethFeed;
    MockChainlinkFeed public usdcFeed;

    address public entryPoint = address(0xEEEE);
    uint256 public rootOwnerPk = 0xAA11;
    address public rootOwner;
    uint256 public sessionKeyPk = 0xBB22;
    address public sessionKey;
    address public guardian = address(0x9999);

    uint256 public constant PASSKEY_QX = 0x111122223333444455556666777788889999AAAABBBBCCCCDDDDEEEEFFFF0001;
    uint256 public constant PASSKEY_QY = 0x22223333444455556666777788889999AAAABBBBCCCCDDDDEEEEFFFF00011112;

    struct GasMetric {
        string contractDomain;
        string methodName;
        uint256 gasUsed;
        uint256 feeWei20Gwei;
        uint256 feeUsdCents;
    }

    GasMetric[] public recordedMetrics;

    function setUp() public {
        rootOwner = vm.addr(rootOwnerPk);
        sessionKey = vm.addr(sessionKeyPk);

        // RIP-7212 native precompile mock at 0x100
        MockRIP7212 ripMock = new MockRIP7212();
        vm.etch(address(0x100), address(ripMock).code);

        validator = new SessionKeyValidator();
        paymaster = new TecPaymaster(entryPoint);
        lidoStaking = new MockDeFiProtocol();
        usdc = new MockERC20("USD Coin", "USDC", 6);

        // Chainlink Feeds
        ethFeed = new MockChainlinkFeed(8, 2500e8, "ETH / USD");
        usdcFeed = new MockChainlinkFeed(8, 1e8, "USDC / USD");

        vm.deal(rootOwner, 50 ether);
        vm.deal(address(this), 50 ether);
    }

    function _createFreshVault() internal returns (TecAccount acc, TetherGuardHook h) {
        h = new TetherGuardHook();
        acc = new TecAccount(entryPoint);
        acc.initialize(rootOwner, address(h), address(validator));
        h.initializeAccountPolicy(address(acc), rootOwner, 1 ether, 2, true, 5 ether);
        vm.deal(address(acc), 50 ether);
        usdc.mint(address(acc), 100_000 * 1e6);
    }

    function _recordGas(string memory domain, string memory method, uint256 gasUsed) internal {
        uint256 feeWei = gasUsed * 20 gwei;
        uint256 feeCents = (feeWei * 2500 * 100) / 1 ether;
        recordedMetrics.push(GasMetric(domain, method, gasUsed, feeWei, feeCents));
    }

    // =========================================================================
    // --- 1. TecAccount Core Gas Benchmarks ---
    // =========================================================================

    function test_Gas_TecAccount_Initialize() public {
        TecAccount freshAccount = new TecAccount(entryPoint);
        TetherGuardHook h = new TetherGuardHook();
        uint256 g0 = gasleft();
        freshAccount.initialize(rootOwner, address(h), address(validator));
        uint256 gUsed = g0 - gasleft();
        _recordGas("TecAccount", "initialize", gUsed);
        assertTrue(freshAccount.rootOwner() == rootOwner);
    }

    function test_Gas_TecAccount_Execute_ETH_UnderLimit() public {
        (TecAccount acc, TetherGuardHook h) = _createFreshVault();
        vm.prank(rootOwner);
        h.setTargetWhitelist(address(acc), address(lidoStaking), true, 2);

        bytes memory callPayload = abi.encodeWithSelector(MockDeFiProtocol.stake.selector);
        bytes memory executionCalldata = abi.encodePacked(address(lidoStaking), uint256(0.1 ether), callPayload);

        vm.prank(rootOwner);
        uint256 g0 = gasleft();
        acc.execute(bytes32(0), executionCalldata);
        uint256 gUsed = g0 - gasleft();
        _recordGas("TecAccount", "execute (Native ETH Stake)", gUsed);
    }

    function test_Gas_TecAccount_Execute_ERC20_Transfer() public {
        (TecAccount acc, TetherGuardHook h) = _createFreshVault();
        vm.prank(rootOwner);
        h.setTargetWhitelist(address(acc), address(usdc), true, 2);

        bytes memory callPayload =
            abi.encodeWithSelector(MockERC20.transfer.selector, address(0x5555), uint256(50 * 1e6));
        bytes memory executionCalldata = abi.encodePacked(address(usdc), uint256(0), callPayload);

        vm.prank(rootOwner);
        uint256 g0 = gasleft();
        acc.execute(bytes32(0), executionCalldata);
        uint256 gUsed = g0 - gasleft();
        _recordGas("TecAccount", "execute (ERC-20 Transfer)", gUsed);
    }

    function test_Gas_TecAccount_ExecuteFromExecutor() public {
        (TecAccount acc, TetherGuardHook h) = _createFreshVault();
        address executor = address(0x8888);
        vm.prank(rootOwner);
        acc.installModule(MODULE_TYPE_EXECUTOR, executor, hex"");

        vm.prank(rootOwner);
        h.setTargetWhitelist(address(acc), address(lidoStaking), true, 2);

        bytes memory callPayload = abi.encodeWithSelector(MockDeFiProtocol.stake.selector);
        bytes memory executionCalldata = abi.encodePacked(address(lidoStaking), uint256(0.05 ether), callPayload);

        vm.prank(executor);
        uint256 g0 = gasleft();
        acc.executeFromExecutor(bytes32(0), executionCalldata);
        uint256 gUsed = g0 - gasleft();
        _recordGas("TecAccount", "executeFromExecutor", gUsed);
    }

    function test_Gas_TecAccount_ModuleLifecycle() public {
        (TecAccount acc,) = _createFreshVault();
        address dummyModule = address(0x7777);

        vm.prank(rootOwner);
        uint256 g0 = gasleft();
        acc.installModule(MODULE_TYPE_EXECUTOR, dummyModule, hex"");
        uint256 gInstall = g0 - gasleft();
        _recordGas("TecAccount", "installModule", gInstall);

        vm.prank(rootOwner);
        uint256 g1 = gasleft();
        acc.uninstallModule(MODULE_TYPE_EXECUTOR, dummyModule, hex"");
        uint256 gUninstall = g1 - gasleft();
        _recordGas("TecAccount", "uninstallModule", gUninstall);
    }

    function test_Gas_TecAccount_ValidateUserOp_DirectECDSA() public {
        TecAccount unvalidatedAccount = new TecAccount(entryPoint);
        unvalidatedAccount.initialize(rootOwner, address(0), address(0));

        bytes32 userOpHash = keccak256("DirectECDSAValidation");
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", userOpHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(rootOwnerPk, ethHash);
        bytes memory sig = abi.encodePacked(r, s, v);

        PackedUserOperation memory op;
        op.sender = address(unvalidatedAccount);
        op.signature = sig;

        vm.prank(entryPoint);
        uint256 g0 = gasleft();
        uint256 valData = unvalidatedAccount.validateUserOp(op, userOpHash, 0);
        uint256 gUsed = g0 - gasleft();
        assertEq(valData, 0);
        _recordGas("TecAccount", "validateUserOp (Direct ECDSA)", gUsed);
    }

    // =========================================================================
    // --- 2. TetherGuardHook Core Gas Benchmarks ---
    // =========================================================================

    function test_Gas_TetherGuardHook_InitializePolicy() public {
        TetherGuardHook h = new TetherGuardHook();
        address dummyAccount = address(0x1234);
        uint256 g0 = gasleft();
        h.initializeAccountPolicy(dummyAccount, rootOwner, 0.5 ether, 2, true, 2 ether);
        uint256 gUsed = g0 - gasleft();
        _recordGas("TetherGuardHook", "initializeAccountPolicy", gUsed);
    }

    function test_Gas_TetherGuardHook_WhitelistingAndPasskey() public {
        (TecAccount acc, TetherGuardHook h) = _createFreshVault();

        vm.prank(rootOwner);
        uint256 g0 = gasleft();
        h.setAccountPasskey(address(acc), PASSKEY_QX, PASSKEY_QY);
        uint256 gPasskey = g0 - gasleft();
        _recordGas("TetherGuardHook", "setAccountPasskey", gPasskey);

        vm.prank(rootOwner);
        uint256 g1 = gasleft();
        h.setTargetWhitelist(address(acc), address(lidoStaking), true, 2);
        uint256 gWhitelist = g1 - gasleft();
        _recordGas("TetherGuardHook", "setTargetWhitelist", gWhitelist);

        vm.prank(rootOwner);
        uint256 g2 = gasleft();
        h.setSessionKeyAuthorization(address(acc), sessionKey, true);
        uint256 gSession = g2 - gasleft();
        _recordGas("TetherGuardHook", "setSessionKeyAuthorization", gSession);
    }

    function test_Gas_TetherGuardHook_BiometricVerification_P256() public {
        (TecAccount acc, TetherGuardHook h) = _createFreshVault();
        vm.prank(rootOwner);
        h.setAccountPasskey(address(acc), PASSKEY_QX, PASSKEY_QY);

        bytes32 challenge = keccak256("BiometricP256VerificationChallenge");
        uint256 r = 0x123456;
        uint256 s = 0xabcdef;
        uint256 deadline = block.timestamp + 5 minutes;

        uint256 g0 = gasleft();
        h.completeBiometricVerificationWithP256(address(acc), challenge, r, s, PASSKEY_QX, PASSKEY_QY, deadline);
        uint256 gP256 = g0 - gasleft();
        _recordGas("TetherGuardHook", "completeBiometricVerificationWithP256 (RIP-7212)", gP256);

        uint256 g1 = gasleft();
        vm.prank(rootOwner);
        h.revokeBiometricVerification(address(acc));
        uint256 gRevoke = g1 - gasleft();
        _recordGas("TetherGuardHook", "revokeBiometricVerification", gRevoke);
    }

    function test_Gas_TetherGuardHook_SubmitSignApproval() public {
        (TecAccount acc, TetherGuardHook h) = _createFreshVault();
        vm.prank(rootOwner);
        h.completeBiometricVerification(address(acc));

        bytes32 execHash = keccak256("TestExecutionCalldata");

        vm.prank(rootOwner);
        uint256 g0 = gasleft();
        h.submitSignApproval(address(acc), execHash, true);
        uint256 gDirect = g0 - gasleft();
        _recordGas("TetherGuardHook", "submitSignApproval (Direct Accept)", gDirect);

        bytes32 msgHash = keccak256(
            abi.encode(
                address(acc),
                execHash,
                true,
                h.signApprovalNonces(address(acc)),
                block.timestamp + 10 minutes,
                block.chainid,
                address(h)
            )
        );
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", msgHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(rootOwnerPk, ethHash);

        uint256 g1 = gasleft();
        h.submitSignApprovalWithSignature(
            address(acc), execHash, true, block.timestamp + 10 minutes, abi.encodePacked(r, s, v)
        );
        uint256 gRelayed = g1 - gasleft();
        _recordGas("TetherGuardHook", "submitSignApprovalWithSignature (Gasless Relay)", gRelayed);
    }

    function test_Gas_TetherGuardHook_MorningReviews() public {
        (TecAccount acc, TetherGuardHook h) = _createFreshVault();
        vm.prank(rootOwner);
        h.setTargetWhitelist(address(acc), address(lidoStaking), true, 2);

        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.1 ether), hex"");
        vm.prank(entryPoint);
        acc.execute(bytes32(0), msgData);

        vm.prank(rootOwner);
        uint256 g0 = gasleft();
        h.ratifyTransaction(address(acc), 1);
        uint256 gLike = g0 - gasleft();
        _recordGas("TetherGuardHook", "ratifyTransaction (Morning Review Ratification)", gLike);

        vm.prank(entryPoint);
        acc.execute(bytes32(0), msgData);

        vm.prank(rootOwner);
        uint256 g1 = gasleft();
        h.flagTransactionForRevert(address(acc), 2, "Unapproved Slippage");
        uint256 gFlag = g1 - gasleft();
        _recordGas("TetherGuardHook", "flagTransactionForRevert (Morning Review Rejection)", gFlag);

        vm.prank(entryPoint);
        acc.execute(bytes32(0), msgData);

        vm.prank(rootOwner);
        uint256 g2 = gasleft();
        h.submitTransactionNote(address(acc), 3, "Execution noted for compliance", false);
        uint256 gNote = g2 - gasleft();
        _recordGas("TetherGuardHook", "submitTransactionNote (Feedback Note)", gNote);
    }

    function test_Gas_TetherGuardHook_DynamicElasticityCalibration() public {
        (TecAccount acc, TetherGuardHook h) = _createFreshVault();
        vm.prank(rootOwner);
        h.setTargetWhitelist(address(acc), address(lidoStaking), true, 2);

        bytes memory msgData = abi.encodePacked(address(lidoStaking), uint256(0.05 ether), hex"");
        vm.prank(entryPoint);
        acc.execute(bytes32(0), msgData);

        vm.prank(rootOwner);
        h.ratifyTransaction(address(acc), 1);

        // Warp 24h past calibration cooldown
        vm.warp(block.timestamp + 25 hours);

        vm.prank(address(acc));
        uint256 g0 = gasleft();
        h.calibrateDynamicRadius(address(acc));
        uint256 gCalib = g0 - gasleft();
        _recordGas("TetherGuardHook", "calibrateDynamicRadius (On-Chain Elasticity)", gCalib);
    }

    function test_Gas_TetherGuardHook_HeartbeatAndDeadman() public {
        (TecAccount acc, TetherGuardHook h) = _createFreshVault();
        vm.prank(rootOwner);
        h.setSessionKeyAuthorization(address(acc), sessionKey, true);

        vm.prank(sessionKey);
        uint256 g0 = gasleft();
        h.recordAIHeartbeat(address(acc));
        uint256 gHb = g0 - gasleft();
        _recordGas("TetherGuardHook", "recordAIHeartbeat (Liveness Ping)", gHb);

        vm.prank(rootOwner);
        uint256 g1 = gasleft();
        h.configureDeadmanSwitch(address(acc), guardian, 90 days);
        uint256 gCfg = g1 - gasleft();
        _recordGas("TetherGuardHook", "configureDeadmanSwitch", gCfg);

        vm.warp(block.timestamp + 91 days);
        vm.prank(guardian);
        uint256 g2 = gasleft();
        h.triggerDeadmanRecovery(address(acc), address(0x1234));
        uint256 gRecovery = g2 - gasleft();
        _recordGas("TetherGuardHook", "triggerDeadmanRecovery (Guardian Recovery)", gRecovery);
    }

    function test_Gas_TetherGuardHook_PortfolioValuation() public {
        (TecAccount acc, TetherGuardHook h) = _createFreshVault();
        address nativeEth = h.NATIVE_ETH();
        vm.prank(rootOwner);
        h.setAccountPriceFeed(address(acc), nativeEth, address(ethFeed));
        vm.prank(rootOwner);
        h.setAccountPriceFeed(address(acc), address(usdc), address(usdcFeed));

        address[] memory tokens = new address[](2);
        tokens[0] = nativeEth;
        tokens[1] = address(usdc);

        uint256 g0 = gasleft();
        h.getTotalPortfolioValueUSD(address(acc), tokens);
        uint256 gUsed = g0 - gasleft();
        _recordGas("TetherGuardHook", "getTotalPortfolioValueUSD (Multi-Asset Valuation)", gUsed);
    }

    // =========================================================================
    // --- 3. SessionKeyValidator Core Gas Benchmarks ---
    // =========================================================================

    function test_Gas_SessionKeyValidator_RegisterAndRevoke() public {
        (TecAccount acc,) = _createFreshVault();
        bytes32 mandateRoot = keccak256("MandateCommitmentBenchmark");

        vm.prank(address(acc));
        uint256 g0 = gasleft();
        validator.registerSessionKey(
            address(acc), sessionKey, uint48(block.timestamp), uint48(block.timestamp + 7 days), mandateRoot
        );
        uint256 gReg = g0 - gasleft();
        _recordGas("SessionKeyValidator", "registerSessionKey", gReg);

        vm.prank(address(acc));
        uint256 g1 = gasleft();
        validator.revokeSessionKey(address(acc), sessionKey);
        uint256 gRev = g1 - gasleft();
        _recordGas("SessionKeyValidator", "revokeSessionKey", gRev);
    }

    function test_Gas_SessionKeyValidator_ValidateUserOp() public {
        (TecAccount acc,) = _createFreshVault();
        bytes32 mandateRoot = keccak256("MandateCommitmentBenchmark");
        vm.prank(address(acc));
        validator.registerSessionKey(
            address(acc), sessionKey, uint48(block.timestamp), uint48(block.timestamp + 7 days), mandateRoot
        );

        bytes32 userOpHash = keccak256("UserOpBenchmark");
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", userOpHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(sessionKeyPk, ethHash);

        bytes memory sig = abi.encodePacked(sessionKey, r, s, v, mandateRoot);

        PackedUserOperation memory op;
        op.sender = address(acc);
        op.signature = sig;

        uint256 g0 = gasleft();
        uint256 valData = validator.validateUserOp(op, userOpHash);
        uint256 gVal = g0 - gasleft();
        assertEq(address(uint160(valData)), address(0));
        _recordGas("SessionKeyValidator", "validateUserOp (with Mandate Root)", gVal);
    }

    function test_Gas_SessionKeyValidator_ERC1271() public {
        (TecAccount acc,) = _createFreshVault();
        bytes32 mandateRoot = keccak256("MandateCommitmentBenchmark");
        vm.prank(address(acc));
        validator.registerSessionKey(
            address(acc), sessionKey, uint48(block.timestamp), uint48(block.timestamp + 7 days), mandateRoot
        );

        bytes32 hash = keccak256("ERC1271Hash");
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", hash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(sessionKeyPk, ethHash);

        bytes memory sig = abi.encodePacked(sessionKey, r, s, v, mandateRoot);

        uint256 g0 = gasleft();
        bytes4 magic = validator.isValidSignatureWithSender(address(acc), hash, sig);
        uint256 gSig = g0 - gasleft();
        assertEq(magic, bytes4(0x1626ba7e));
        _recordGas("SessionKeyValidator", "isValidSignatureWithSender (ERC-1271)", gSig);
    }

    // =========================================================================
    // --- 4. TecPaymaster Core Gas Benchmarks ---
    // =========================================================================

    function test_Gas_TecPaymaster_Operations() public {
        (TecAccount acc,) = _createFreshVault();

        uint256 g0 = gasleft();
        paymaster.depositForAccount{value: 1 ether}(address(acc));
        uint256 gDep = g0 - gasleft();
        _recordGas("TecPaymaster", "depositForAccount", gDep);

        PackedUserOperation memory op;
        op.sender = address(acc);
        op.signature = abi.encodePacked(sessionKey, hex"1234");

        uint256 g1 = gasleft();
        (bytes memory ctx, uint256 valData) = paymaster.validatePaymasterUserOp(op, bytes32(0), 0.001 ether);
        uint256 gVal = g1 - gasleft();
        assertEq(valData, 0);
        _recordGas("TecPaymaster", "validatePaymasterUserOp (Anti-Grief Check)", gVal);

        vm.prank(entryPoint);
        uint256 g2 = gasleft();
        paymaster.postOp(IPaymaster.PostOpMode.opSucceeded, ctx, 0.0008 ether, 1 gwei);
        uint256 gPost = g2 - gasleft();
        _recordGas("TecPaymaster", "postOp (Gas Accounting)", gPost);

        vm.prank(address(acc));
        uint256 g3 = gasleft();
        paymaster.withdrawForAccount(payable(address(0x1111)), 0.2 ether);
        uint256 gWithUser = g3 - gasleft();
        _recordGas("TecPaymaster", "withdrawForAccount (User Self-Refund)", gWithUser);

        (bool s,) = address(paymaster).call{value: 0.5 ether}("");
        assertTrue(s);
        uint256 g4 = gasleft();
        paymaster.withdraw(payable(address(this)), 0.5 ether);
        uint256 gWithSurplus = g4 - gasleft();
        _recordGas("TecPaymaster", "withdraw (Owner Surplus Refund)", gWithSurplus);

        uint256 g5 = gasleft();
        paymaster.depositToEntryPoint{value: 0.1 ether}();
        uint256 gEP = g5 - gasleft();
        _recordGas("TecPaymaster", "depositToEntryPoint", gEP);
    }

    // =========================================================================
    // --- 5. Unified Empirical Summary Table Output ---
    // =========================================================================

    function test_UnifiedEmpiricalGasBenchmarkMatrix() public {
        delete recordedMetrics;

        test_Gas_TecAccount_Initialize();
        test_Gas_TecAccount_Execute_ETH_UnderLimit();
        test_Gas_TecAccount_Execute_ERC20_Transfer();
        test_Gas_TecAccount_ExecuteFromExecutor();
        test_Gas_TecAccount_ModuleLifecycle();
        test_Gas_TecAccount_ValidateUserOp_DirectECDSA();
        test_Gas_TetherGuardHook_InitializePolicy();
        test_Gas_TetherGuardHook_WhitelistingAndPasskey();
        test_Gas_TetherGuardHook_BiometricVerification_P256();
        test_Gas_TetherGuardHook_SubmitSignApproval();
        test_Gas_TetherGuardHook_MorningReviews();
        test_Gas_TetherGuardHook_DynamicElasticityCalibration();
        test_Gas_TetherGuardHook_HeartbeatAndDeadman();
        test_Gas_TetherGuardHook_PortfolioValuation();
        test_Gas_SessionKeyValidator_RegisterAndRevoke();
        test_Gas_SessionKeyValidator_ValidateUserOp();
        test_Gas_SessionKeyValidator_ERC1271();
        test_Gas_TecPaymaster_Operations();

        console.log(
            "===================================================================================================="
        );
        console.log(
            "                    TEC-C ON-CHAIN VAULT: EMPIRICAL TRANSACTION FEE MATRIX                          "
        );
        console.log(
            "         Base Fee: 20 Gwei (Mainnet Standard) | Base Fee: 50 Gwei (Congestion) | ETH = $2,500 USD   "
        );
        console.log(
            "===================================================================================================="
        );
        console.log(
            "| Contract Domain       | Method Name                                   | Gas Used | Fee @ 20 Gwei | Fee (USD) | Fee @ 50 Gwei |"
        );
        console.log(
            "|:----------------------|:----------------------------------------------|:---------|:--------------|:----------|:--------------|"
        );

        for (uint256 i = 0; i < recordedMetrics.length; i++) {
            GasMetric memory m = recordedMetrics[i];
            uint256 fee50Gwei = m.gasUsed * 50 gwei;
            uint256 cents = m.feeUsdCents;
            string memory centStr =
                cents % 100 < 10 ? string.concat("0", vm.toString(cents % 100)) : vm.toString(cents % 100);

            console.log(
                string.concat(
                    "| ",
                    m.contractDomain,
                    " | ",
                    m.methodName,
                    " | ",
                    vm.toString(m.gasUsed),
                    " | ",
                    vm.toString(m.feeWei20Gwei),
                    " wei | $",
                    vm.toString(cents / 100),
                    ".",
                    centStr,
                    " | ",
                    vm.toString(fee50Gwei),
                    " wei |"
                )
            );
        }
        console.log(
            "===================================================================================================="
        );
    }

    receive() external payable {}
}

// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test, console} from "forge-std/Test.sol";
import {WebAuthnP256Validator} from "../src/validators/WebAuthnP256Validator.sol";
import {P256Verifier} from "../src/validators/P256Verifier.sol";
import {TetherGuardHook} from "../src/hooks/TetherGuardHook.sol";
import {PortfolioValuator} from "../src/hooks/PortfolioValuator.sol";
import {MockRIP7212} from "./mocks/MockRIP7212.sol";
import {PackedUserOperation} from "../src/interfaces/PackedUserOperation.sol";

contract WebAuthnP256ValidatorTest is Test {
    WebAuthnP256Validator public validator;
    TetherGuardHook public hook;
    MockRIP7212 public mockPrecompile;

    address public tecAccount = address(0xBB22);
    address public rootOwner = address(0xAA11);
    address public guardian = address(0xCC33);

    // Simulated P-256 coordinates from an iPhone Secure Enclave (Face ID)
    uint256 public constant PASSKEY_QX = 0x5821017c667a6d8d9b1a5e3f4c2b1a0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a;
    uint256 public constant PASSKEY_QY = 0x203541f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3;

    // RFC 6979 Appendix A.2.5 Official NIST P-256 Test Vector (Real Curve Point & Signature over SHA256("sample"))
    uint256 public constant RFC6979_QX = 0x60FED4BA255A9D31C961EB74C6356D68C049B8923B61FA6CE669622E60F29FB6;
    uint256 public constant RFC6979_QY = 0x7903FE1008B8BC99A41AE9E95628BC64F2F1B20C2D7E9F5177A3C294D4462299;
    bytes32 public constant RFC6979_MSG_HASH = 0xAF2BDBE1AA9B6EC1E2ADE1D694F41FC71A831D0268E9891562113D8A62ADD1BF;
    uint256 public constant RFC6979_R = 0xEFD48B2AACB6A8FD1140DD9CD45E81D69D2C877B56AAF991C34D0EA84EAF3716;
    uint256 public constant RFC6979_S_HIGH = 0xF7CB1C942D657C41D436C7A1B6E29F65F3E900DBB9AFF4064DC4AB2F843ACDA8;
    uint256 public constant RFC6979_S_LOW = P256Verifier.P256_N - RFC6979_S_HIGH;

    function setUp() public {
        // Deploy and etch MockRIP7212 to exact RIP-7212 precompile address 0x100
        mockPrecompile = new MockRIP7212();
        vm.etch(address(0x100), address(mockPrecompile).code);

        validator = new WebAuthnP256Validator();
        hook = new TetherGuardHook(address(new PortfolioValuator()));
        hook.setFallbackP256Verifier(address(validator));

        hook.initializeAccountPolicy(tecAccount, rootOwner, 0.5 ether, 2);

        // Register hardware passkey for tecAccount
        vm.prank(tecAccount);
        validator.registerPasskey(tecAccount, PASSKEY_QX, PASSKEY_QY);

        // Register hardware passkey on hook
        vm.prank(tecAccount);
        hook.setAccountPasskey(tecAccount, PASSKEY_QX, PASSKEY_QY);
    }

    function test_PasskeyRegistration() public view {
        (uint256 qx, uint256 qy, bool isReg) = validator.passkeys(tecAccount);
        assertEq(qx, PASSKEY_QX);
        assertEq(qy, PASSKEY_QY);
        assertTrue(isReg);
    }

    function test_VerifyP256Signature_NativePrecompile_Success() public view {
        bytes32 messageHash = keccak256("WebAuthn Auth: Execute Transaction");
        uint256 r = 0x1234567890;
        uint256 s = 0xabcdef1234;

        bool isValid = validator.verifyP256Signature(messageHash, r, s, PASSKEY_QX, PASSKEY_QY);
        assertTrue(isValid);
    }

    function test_VerifyP256Signature_InvalidSignature_Fails() public view {
        bytes32 messageHash = keccak256("WebAuthn Auth: Execute Transaction");
        uint256 r = 0xDEAD; // Signal intentional failure to mock
        uint256 s = 0xDEAD;

        bool isValid = validator.verifyP256Signature(messageHash, r, s, PASSKEY_QX, PASSKEY_QY);
        assertFalse(isValid);
    }

    function test_ValidateUserOp_Success() public view {
        bytes32 userOpHash = keccak256("UserOp_001");
        uint256 r = 0x112233;
        uint256 s = 0x445566;

        bytes memory signature = abi.encode(r, s);

        PackedUserOperation memory op;
        op.sender = tecAccount;
        op.signature = signature;

        uint256 validationData = validator.validateUserOp(op, userOpHash);
        assertEq(validationData, 0); // 0 = Valid signature
    }

    function test_ValidateUserOp_UnregisteredPasskey_Fails() public view {
        PackedUserOperation memory op;
        op.sender = address(0x9999); // Unregistered account
        op.signature = abi.encode(uint256(1), uint256(2));

        uint256 validationData = validator.validateUserOp(op, bytes32(0));
        assertEq(validationData, 1); // 1 = Validation failure
    }

    function test_EIP1271_PasskeySignatureValidation() public view {
        bytes32 hash = keccak256("EIP-712 Mandate Approval");
        bytes memory data = abi.encode(uint256(123), uint256(456));

        bytes4 magic = validator.isValidSignatureWithSender(tecAccount, hash, data);
        assertTrue(magic == 0x1626ba7e); // EIP-1271 magic value
    }

    function test_CompleteBiometricVerificationWithP256_OpensWindow() public {
        bytes32 challenge = keccak256("Breakout Challenge: 10 ETH Allocation");
        uint256 r = 0x778899;
        uint256 s = 0xaabbcc;

        // User verifies FaceID via RIP-7212 P-256 precompile
        hook.completeBiometricVerificationWithP256(tecAccount, challenge, r, s, PASSKEY_QX, PASSKEY_QY);

        // 5-minute Biometric Verification window is now active!
        assertTrue(hook.isBiometricActive(tecAccount));
        assertEq(hook.biometricVerifiedUntil(tecAccount), block.timestamp + 5 minutes);
    }

    function test_CompleteBiometricVerificationWithP256_InvalidSignature_Reverts() public {
        bytes32 challenge = keccak256("Breakout Challenge: 10 ETH Allocation");
        uint256 r = 0xDEAD; // Invalid signature
        uint256 s = 0xDEAD;

        vm.expectRevert(TetherGuardHook.InvalidP256Signature.selector);
        hook.completeBiometricVerificationWithP256(tecAccount, challenge, r, s, PASSKEY_QX, PASSKEY_QY);
    }

    function test_CompleteBiometricVerificationWithP256_UnregisteredPasskey_Reverts() public {
        bytes32 challenge = keccak256("Breakout Challenge: 10 ETH Allocation");
        uint256 r = 0x778899;
        uint256 s = 0xaabbcc;
        uint256 fakeQx = 0x1111;
        uint256 fakeQy = 0x2222;

        vm.expectRevert(TetherGuardHook.UnauthorizedPasskey.selector);
        hook.completeBiometricVerificationWithP256(tecAccount, challenge, r, s, fakeQx, fakeQy);
    }

    function test_ValidateUserOp_EnvelopeChallengeMismatch_Fails() public view {
        bytes32 realUserOpHash = keccak256("RealUserOpHash");
        bytes32 fakeChallenge = keccak256("FakeReplayedChallenge");
        uint256 r = 0x112233;
        uint256 s = 0x445566;

        bytes memory signature = abi.encode(r, s, fakeChallenge);

        PackedUserOperation memory op;
        op.sender = tecAccount;
        op.signature = signature;

        uint256 validationData = validator.validateUserOp(op, realUserOpHash);
        assertEq(validationData, 1); // 1 = Validation failure (Challenge mismatch)
    }

    function test_ValidateUserOp_EnvelopeChallengeMatch_Success() public view {
        bytes32 realUserOpHash = keccak256("RealUserOpHash");
        uint256 r = 0x112233;
        uint256 s = 0x445566;

        bytes memory signature = abi.encode(r, s, realUserOpHash);

        PackedUserOperation memory op;
        op.sender = tecAccount;
        op.signature = signature;

        uint256 validationData = validator.validateUserOp(op, realUserOpHash);
        assertEq(validationData, 0); // 0 = Valid signature
    }

    // =========================================================================
    // Nuance 1: RIP-7212 Precompile Fallback to Pure-Solidity P-256 on L1 / FISCO BCOS
    // =========================================================================

    function test_Nuance1_PureSolidityFallback_WhenPrecompile0x100Absent_EthereumL1AndFisco() public {
        // Erase 0x100 precompile bytecode to simulate Ethereum L1 Mainnet or FISCO BCOS without RIP-7212
        vm.etch(address(0x100), hex"");
        assertEq(address(0x100).code.length, 0);

        // Register the real NIST P-256 RFC 6979 public key on both validator and hook
        bytes32 rfcKeyId = keccak256("RFC6979_REAL_HARDWARE_KEY");
        vm.startPrank(tecAccount);
        validator.addPasskey(tecAccount, rfcKeyId, RFC6979_QX, RFC6979_QY);
        hook.addAccountPasskey(tecAccount, rfcKeyId, RFC6979_QX, RFC6979_QY);
        vm.stopPrank();

        // 1. Verify real NIST P-256 signature via pure-Solidity Jacobian math (with 0x100 absent!)
        bool validOnL1 =
            validator.verifyP256Signature(RFC6979_MSG_HASH, RFC6979_R, RFC6979_S_LOW, RFC6979_QX, RFC6979_QY);
        assertTrue(validOnL1, "Pure-Solidity P-256 verifier must validate real RFC 6979 signature on L1");

        // 2. Verify corrupted signature fails in pure-Solidity fallback
        bool invalidOnL1 =
            validator.verifyP256Signature(RFC6979_MSG_HASH, RFC6979_R + 1, RFC6979_S_LOW, RFC6979_QX, RFC6979_QY);
        assertFalse(invalidOnL1, "Tampered R must fail pure-Solidity P-256 verification");

        // 3. Complete Biometric Verification on TetherGuardHook using pure-Solidity fallback
        hook.completeBiometricVerificationWithP256(
            tecAccount, RFC6979_MSG_HASH, RFC6979_R, RFC6979_S_LOW, RFC6979_QX, RFC6979_QY
        );
        assertTrue(hook.isBiometricActive(tecAccount));
    }

    // =========================================================================
    // Nuance 2: Signature Malleability Protection (s <= n/2)
    // =========================================================================

    function test_Nuance2_SignatureMalleability_HighS_Rejected() public {
        // RFC6979_S_HIGH is > P256_N / 2 (malleable upper-half S value)
        assertTrue(RFC6979_S_HIGH > validator.P256_N_DIV_2());
        assertTrue(RFC6979_S_LOW <= validator.P256_N_DIV_2());

        // 1. Validator rejects high-S signature
        bool validHighS =
            validator.verifyP256Signature(RFC6979_MSG_HASH, RFC6979_R, RFC6979_S_HIGH, PASSKEY_QX, PASSKEY_QY);
        assertFalse(validHighS, "High-S malleable signature must be rejected");

        // 2. ERC-4337 validateUserOp rejects high-S signature
        PackedUserOperation memory op;
        op.sender = tecAccount;
        op.signature = abi.encode(RFC6979_R, RFC6979_S_HIGH);
        assertEq(validator.validateUserOp(op, RFC6979_MSG_HASH), 1);

        // 3. TetherGuardHook reverts with MalleableP256Signature
        vm.expectRevert(TetherGuardHook.MalleableP256Signature.selector);
        hook.completeBiometricVerificationWithP256(
            tecAccount, RFC6979_MSG_HASH, RFC6979_R, RFC6979_S_HIGH, PASSKEY_QX, PASSKEY_QY
        );
    }

    // =========================================================================
    // Nuance 3: On-Chain WebAuthn authenticatorData Flags (UP = 0x01, UV = 0x04)
    // =========================================================================

    function _buildAuthData(uint8 flags) internal pure returns (bytes memory) {
        bytes32 rpIdHash = sha256("tecc.finance");
        uint32 signCount = 1;
        return abi.encodePacked(rpIdHash, flags, signCount);
    }

    function test_Nuance3_AuthenticatorDataFlags_UVBitRequiredForBiometricTetherBreak() public {
        bytes32 clientDataHash = keccak256("Challenge_HighValue_TetherBreak");
        uint256 r = 0x11223344;
        uint256 s = 0x55667788;

        // Case 1: Passive keypress (UP = 0x01 set, but UV = 0x04 NOT set -> flags = 0x01)
        bytes memory passiveAuthData = _buildAuthData(0x01);

        // Validator rejects when requireUserVerification == true
        assertFalse(
            validator.verifyWebAuthnSignature(passiveAuthData, clientDataHash, r, s, PASSKEY_QX, PASSKEY_QY, true)
        );

        // ERC-4337 Full WebAuthn UserOp rejects when UV bit is missing
        PackedUserOperation memory opPassive;
        opPassive.sender = tecAccount;
        opPassive.signature = abi.encode(passiveAuthData, clientDataHash, r, s, PASSKEY_QX, PASSKEY_QY);
        assertEq(validator.validateUserOp(opPassive, clientDataHash), 1);

        // TetherGuardHook reverts with BiometricUserVerificationRequired
        vm.expectRevert(TetherGuardHook.BiometricUserVerificationRequired.selector);
        hook.completeBiometricVerificationWithWebAuthn(
            tecAccount, passiveAuthData, clientDataHash, r, s, PASSKEY_QX, PASSKEY_QY, block.timestamp + 5 minutes
        );

        // Case 2: True Biometric Face ID verification (UP = 0x01 | UV = 0x04 -> flags = 0x05)
        bytes memory biometricAuthData = _buildAuthData(0x05);
        assertTrue(
            validator.verifyWebAuthnSignature(biometricAuthData, clientDataHash, r, s, PASSKEY_QX, PASSKEY_QY, true)
        );

        PackedUserOperation memory opBiometric;
        opBiometric.sender = tecAccount;
        opBiometric.signature = abi.encode(biometricAuthData, clientDataHash, r, s, PASSKEY_QX, PASSKEY_QY);
        assertEq(validator.validateUserOp(opBiometric, clientDataHash), 0);

        hook.completeBiometricVerificationWithWebAuthn(
            tecAccount, biometricAuthData, clientDataHash, r, s, PASSKEY_QX, PASSKEY_QY, block.timestamp + 5 minutes
        );
        assertTrue(hook.isBiometricActive(tecAccount));
    }

    // =========================================================================
    // Nuance 4: Multi-Device Passkeys & Emergency Guardian Account Recovery
    // =========================================================================

    function test_Nuance4_MultiDevicePasskeys_And_EmergencyGuardianRecovery() public {
        bytes32 macbookKeyId = keccak256("MacBook-Pro-FaceID");
        uint256 macQx = 0x1111222233334444555566667777888899990000aaaabbbbccccddddeeeeffff;
        uint256 macQy = 0x9999888877776666555544443333222211110000ffffeeeeddddccccbbbbaaaa;

        // 1. Register backup MacBook passkey alongside primary iPhone passkey
        vm.startPrank(tecAccount);
        validator.addPasskey(tecAccount, macbookKeyId, macQx, macQy);
        hook.addAccountPasskey(tecAccount, macbookKeyId, macQx, macQy);
        vm.stopPrank();

        assertEq(validator.activePasskeyCount(tecAccount), 2);
        assertEq(hook.activeAccountPasskeyCount(tecAccount), 2);
        assertTrue(validator.isAuthorizedPasskey(tecAccount, macQx, macQy));
        assertTrue(hook.isAuthorizedAccountPasskey(tecAccount, macQx, macQy));

        // 2. Backup MacBook passkey can open the 5-minute biometric window on TetherGuardHook
        bytes32 challenge1 = keccak256("MacBook_Backup_Breakout");
        hook.completeBiometricVerificationWithP256(tecAccount, challenge1, 0x1234, 0x5678, macQx, macQy);
        assertTrue(hook.isBiometricActive(tecAccount));

        // 3. User loses primary iPhone in the ocean -> revokes primary passkey while MacBook remains active
        bytes32 primaryId = validator.PRIMARY_KEY_ID();
        vm.startPrank(tecAccount);
        validator.revokePasskeyById(tecAccount, primaryId);
        hook.revokeAccountPasskey(tecAccount, primaryId);
        vm.stopPrank();

        assertEq(validator.activePasskeyCount(tecAccount), 1);
        assertFalse(validator.isAuthorizedPasskey(tecAccount, PASSKEY_QX, PASSKEY_QY));
        assertTrue(validator.isAuthorizedPasskey(tecAccount, macQx, macQy));

        // Attempting to revoke the last remaining passkey reverts to prevent self-lockout
        vm.prank(tecAccount);
        vm.expectRevert(WebAuthnP256Validator.CannotRevokeLastPasskey.selector);
        validator.revokePasskeyById(tecAccount, macbookKeyId);

        // 4. Configure Emergency Recovery Guardian & recover with a brand-new device passkey
        vm.startPrank(tecAccount);
        validator.setRecoveryGuardian(tecAccount, guardian);
        hook.setPasskeyRecoveryGuardian(tecAccount, guardian);
        vm.stopPrank();

        bytes32 newPhoneId = keccak256("iPhone-17-Pro-Replacement");
        uint256 newQx = 0xaaaa0000bbbb1111cccc2222dddd3333eeee4444ffff55556666777788889999;
        uint256 newQy = 0x123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0;

        // Unauthorized attacker cannot trigger guardian recovery
        vm.prank(address(0xBAD));
        vm.expectRevert(WebAuthnP256Validator.UnauthorizedGuardian.selector);
        validator.recoverPasskey(tecAccount, newPhoneId, newQx, newQy);

        // Designated guardian executes recovery
        vm.startPrank(guardian);
        validator.recoverPasskey(tecAccount, newPhoneId, newQx, newQy);
        hook.recoverAccountPasskey(tecAccount, newPhoneId, newQx, newQy);
        vm.stopPrank();

        assertTrue(validator.isAuthorizedPasskey(tecAccount, newQx, newQy));
        assertTrue(hook.isAuthorizedAccountPasskey(tecAccount, newQx, newQy));
    }
}

// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import { Test, console } from "forge-std/Test.sol";
import { WebAuthnP256Validator } from "../src/validators/WebAuthnP256Validator.sol";
import { TetherGuardHook } from "../src/hooks/TetherGuardHook.sol";
import { MockRIP7212 } from "./mocks/MockRIP7212.sol";
import { PackedUserOperation } from "../src/interfaces/PackedUserOperation.sol";

contract WebAuthnP256ValidatorTest is Test {
    WebAuthnP256Validator public validator;
    TetherGuardHook public hook;
    MockRIP7212 public mockPrecompile;

    address public tecAccount = address(0xBB22);
    address public rootOwner = address(0xAA11);

    // Simulated P-256 coordinates from an iPhone Secure Enclave (TouchID/FaceID)
    uint256 public constant PASSKEY_QX = 0x5821017c667a6d8d9b1a5e3f4c2b1a0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a;
    uint256 public constant PASSKEY_QY = 0x203541f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3;

    function setUp() public {
        // Deploy and etch MockRIP7212 to exact RIP-7212 precompile address 0x100
        mockPrecompile = new MockRIP7212();
        vm.etch(address(0x100), address(mockPrecompile).code);

        validator = new WebAuthnP256Validator();
        hook = new TetherGuardHook();

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
        hook.completeBiometricVerificationWithP256(
            tecAccount,
            challenge,
            r,
            s,
            PASSKEY_QX,
            PASSKEY_QY
        );

        // 5-minute Biometric Verification window is now active!
        assertTrue(hook.isBiometricActive(tecAccount));
        assertEq(hook.biometricVerifiedUntil(tecAccount), block.timestamp + 5 minutes);
    }

    function test_CompleteBiometricVerificationWithP256_InvalidSignature_Reverts() public {
        bytes32 challenge = keccak256("Breakout Challenge: 10 ETH Allocation");
        uint256 r = 0xDEAD; // Invalid signature
        uint256 s = 0xDEAD;

        vm.expectRevert(TetherGuardHook.InvalidP256Signature.selector);
        hook.completeBiometricVerificationWithP256(
            tecAccount,
            challenge,
            r,
            s,
            PASSKEY_QX,
            PASSKEY_QY
        );
    }

    function test_CompleteBiometricVerificationWithP256_UnregisteredPasskey_Reverts() public {
        bytes32 challenge = keccak256("Breakout Challenge: 10 ETH Allocation");
        uint256 r = 0x778899;
        uint256 s = 0xaabbcc;
        uint256 fakeQx = 0x1111;
        uint256 fakeQy = 0x2222;

        vm.expectRevert(TetherGuardHook.UnauthorizedPasskey.selector);
        hook.completeBiometricVerificationWithP256(
            tecAccount,
            challenge,
            r,
            s,
            fakeQx,
            fakeQy
        );
    }
}

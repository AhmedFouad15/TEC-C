// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import { Test, console } from "forge-std/Test.sol";
import { SessionKeyValidator } from "../src/validators/SessionKeyValidator.sol";
import { PackedUserOperation } from "../src/interfaces/PackedUserOperation.sol";

contract SessionKeyValidatorTest is Test {
    SessionKeyValidator public validator;

    address public tecAccount = address(0xBB22);
    uint256 public sessionKeyPrivateKey = 0xA11CE;
    address public sessionKey;

    bytes32 public mandateRoot = keccak256("WeIdentity:Mandate:Conservative:ShiborStake");

    function setUp() public {
        validator = new SessionKeyValidator();
        sessionKey = vm.addr(sessionKeyPrivateKey);

        // Register session key valid from block.timestamp to block.timestamp + 2 hours
        uint48 validAfter = uint48(block.timestamp);
        uint48 validUntil = uint48(block.timestamp + 2 hours);

        vm.prank(tecAccount);
        validator.registerSessionKey(tecAccount, sessionKey, validAfter, validUntil, mandateRoot);
    }

    function test_SessionKeyRegistration() public view {
        (
            address key,
            uint48 validAfter,
            uint48 validUntil,
            bytes32 root,
            bool isActive
        ) = validator.sessionKeys(tecAccount, sessionKey);

        assertEq(key, sessionKey);
        assertEq(validAfter, uint48(block.timestamp));
        assertEq(validUntil, uint48(block.timestamp + 2 hours));
        assertEq(root, mandateRoot);
        assertTrue(isActive);
    }

    function test_ValidateUserOp_Success() public view {
        bytes32 userOpHash = keccak256("TestUserOperationHash");
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", userOpHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(sessionKeyPrivateKey, ethHash);

        bytes memory signature = abi.encodePacked(sessionKey, r, s, v);

        PackedUserOperation memory userOp;
        userOp.sender = tecAccount;
        userOp.signature = signature;

        uint256 validationData = validator.validateUserOp(userOp, userOpHash);

        // Authorizer status is 0 (first 160 bits = 0)
        assertEq(address(uint160(validationData)), address(0));
    }

    function test_ValidateUserOp_WrongSigner_Fails() public view {
        bytes32 userOpHash = keccak256("TestUserOperationHash");
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", userOpHash));

        // Sign with an unauthorized private key
        uint256 attackerKey = 0xBAD;
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(attackerKey, ethHash);

        bytes memory signature = abi.encodePacked(sessionKey, r, s, v);

        PackedUserOperation memory userOp;
        userOp.sender = tecAccount;
        userOp.signature = signature;

        uint256 validationData = validator.validateUserOp(userOp, userOpHash);
        assertEq(validationData, 1); // Sig failed
    }

    function test_ValidateUserOp_RevokedSessionKey_Fails() public {
        vm.prank(tecAccount);
        validator.revokeSessionKey(tecAccount, sessionKey);

        bytes32 userOpHash = keccak256("TestUserOperationHash");
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", userOpHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(sessionKeyPrivateKey, ethHash);

        bytes memory signature = abi.encodePacked(sessionKey, r, s, v);

        PackedUserOperation memory userOp;
        userOp.sender = tecAccount;
        userOp.signature = signature;

        uint256 validationData = validator.validateUserOp(userOp, userOpHash);
        assertEq(validationData, 1);
    }

    function test_ERC1271_SignatureValidation() public view {
        bytes32 dataHash = keccak256("MandateAuthorizationDigest");
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", dataHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(sessionKeyPrivateKey, ethHash);

        bytes memory signature = abi.encodePacked(sessionKey, r, s, v);

        bytes4 magic = validator.isValidSignatureWithSender(tecAccount, dataHash, signature);
        assertEq(magic, bytes4(0x1626ba7e)); // EIP-1271 success
    }

    function test_ERC1271_ExpiredSignature_Fails() public {
        bytes32 dataHash = keccak256("MandateAuthorizationDigest");
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", dataHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(sessionKeyPrivateKey, ethHash);

        bytes memory signature = abi.encodePacked(sessionKey, r, s, v);

        // Fast forward 3 hours (past 2-hour validity window)
        vm.warp(block.timestamp + 3 hours);

        bytes4 magic = validator.isValidSignatureWithSender(tecAccount, dataHash, signature);
        assertEq(magic, bytes4(0xffffffff)); // EIP-1271 failed
    }

    function test_VerifyMandateCommitment_Success() public view {
        (bool isValid, bytes32 root) = validator.verifyMandateCommitment(tecAccount, sessionKey, mandateRoot);
        assertTrue(isValid);
        assertEq(root, mandateRoot);
    }

    function test_VerifyMandateCommitment_Mismatch_Fails() public view {
        bytes32 wrongDigest = keccak256("WrongMandateDigest");
        (bool isValid, bytes32 root) = validator.verifyMandateCommitment(tecAccount, sessionKey, wrongDigest);
        assertFalse(isValid);
        assertEq(root, mandateRoot);
    }
}

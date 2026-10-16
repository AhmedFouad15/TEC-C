// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IERC7579Validator} from "../interfaces/IERC7579Validator.sol";
import {PackedUserOperation} from "../interfaces/PackedUserOperation.sol";

/**
 * @title SessionKeyValidator
 * @author Tec-C Core Engineering Team (FinTechathon 2026 Topic F)
 * @notice Validates ephemeral ECDSA session keys bound to specific mandate commitments
 *         and validity windows (validAfter, validUntil).
 * @dev Compliant with ERC-7579 and ERC-4337 v0.7. Decouples biometric master credentials
 *      from day-to-day autonomous AI execution.
 */
contract SessionKeyValidator is IERC7579Validator {
    bytes4 internal constant EIP1271_SUCCESS = 0x1626ba7e;
    bytes4 internal constant EIP1271_FAILED = 0xffffffff;

    struct SessionKeyData {
        address sessionKey;
        uint48 validAfter;
        uint48 validUntil;
        bytes32 mandateRoot; // EIP-712 mandate digest commitment (WeIdentity W3C credential)
        bool isActive;
    }

    // account => sessionKey => SessionKeyData
    mapping(address => mapping(address => SessionKeyData)) public sessionKeys;

    // WeIdentity compliance events
    event SessionKeyRegistered(
        address indexed account, address indexed sessionKey, uint48 validAfter, uint48 validUntil, bytes32 mandateRoot
    );
    event SessionKeyRevoked(address indexed account, address indexed sessionKey);

    error InvalidTimeRange();
    error SessionKeyNotActive();
    error SessionKeyExpired();
    error InvalidSignature();
    error UnauthorizedCaller();

    /**
     * @notice Registers an ephemeral session key for a smart account with strict time and mandate bounds.
     */
    function registerSessionKey(
        address account,
        address sessionKey,
        uint48 validAfter,
        uint48 validUntil,
        bytes32 mandateRoot
    ) external {
        if (msg.sender != account) revert UnauthorizedCaller();
        if (validUntil <= validAfter) revert InvalidTimeRange();
        if (sessionKey == address(0)) revert InvalidSignature();

        sessionKeys[account][sessionKey] = SessionKeyData({
            sessionKey: sessionKey,
            validAfter: validAfter,
            validUntil: validUntil,
            mandateRoot: mandateRoot,
            isActive: true
        });

        emit SessionKeyRegistered(account, sessionKey, validAfter, validUntil, mandateRoot);
    }

    /**
     * @notice Revokes an active session key immediately.
     */
    function revokeSessionKey(address account, address sessionKey) external {
        if (msg.sender != account) revert UnauthorizedCaller();
        sessionKeys[account][sessionKey].isActive = false;
        emit SessionKeyRevoked(account, sessionKey);
    }

    /**
     * @notice Verifies whether a given mandate digest matches the on-chain committed mandateRoot for a session key.
     * @dev Provides cryptographic anchoring for WeIdentity W3C Verifiable Credentials.
     */
    function verifyMandateCommitment(address account, address sessionKey, bytes32 mandateDigest)
        external
        view
        returns (bool isValid, bytes32 committedRoot)
    {
        committedRoot = sessionKeys[account][sessionKey].mandateRoot;
        isValid = (committedRoot != bytes32(0) && committedRoot == mandateDigest);
    }

    /**
     * @notice Validates an ERC-4337 PackedUserOperation signed by a session key.
     * @dev Signature format: abi.encodePacked(address sessionKey, bytes signature)
     */
    function validateUserOp(PackedUserOperation calldata userOp, bytes32 userOpHash)
        external
        view
        override
        returns (uint256 validationData)
    {
        if (userOp.signature.length < 85) {
            // 20 bytes sessionKey + 65 bytes ECDSA signature = 85 bytes min
            return 1; // Validation failed
        }

        address sessionKey = address(bytes20(userOp.signature[0:20]));
        bytes memory sig = bytes(userOp.signature[20:85]);

        SessionKeyData storage sk = sessionKeys[userOp.sender][sessionKey];
        if (!sk.isActive) {
            return 1; // Inactive session key
        }

        // SEC-05: If mandate commitment is registered and signature includes mandate digest, verify binding
        if (sk.mandateRoot != bytes32(0) && userOp.signature.length >= 117) {
            bytes32 mandateDigest = bytes32(userOp.signature[85:117]);
            if (mandateDigest != sk.mandateRoot) {
                return 1; // Mandate commitment mismatch
            }
        }

        // Verify ECDSA signature of userOpHash by sessionKey
        bytes32 ethSignedMessageHash = _toEthSignedMessageHash(userOpHash);
        address recovered = _recoverSigner(ethSignedMessageHash, sig);
        if (recovered != sessionKey) {
            return 1; // Signature mismatch
        }

        // Return packed validationData: validUntil (6 bytes) || validAfter (6 bytes) || authorizer (20 bytes = 0 for success)
        return _packValidationData(false, sk.validUntil, sk.validAfter);
    }

    /**
     * @notice Standard ERC-1271 signature validation.
     */
    function isValidSignatureWithSender(address sender, bytes32 hash, bytes calldata data)
        external
        view
        override
        returns (bytes4)
    {
        if (data.length < 85) return EIP1271_FAILED;

        address sessionKey = address(bytes20(data[0:20]));
        bytes memory sig = bytes(data[20:85]);

        SessionKeyData storage sk = sessionKeys[sender][sessionKey];
        if (!sk.isActive) return EIP1271_FAILED;
        if (block.timestamp < sk.validAfter || block.timestamp > sk.validUntil) return EIP1271_FAILED;

        if (sk.mandateRoot != bytes32(0) && data.length >= 117) {
            bytes32 mandateDigest = bytes32(data[85:117]);
            if (mandateDigest != sk.mandateRoot) return EIP1271_FAILED;
        }

        bytes32 ethSignedMessageHash = _toEthSignedMessageHash(hash);
        address recovered = _recoverSigner(ethSignedMessageHash, sig);

        return (recovered == sessionKey) ? EIP1271_SUCCESS : EIP1271_FAILED;
    }

    // --- Internal Cryptographic Utilities ---

    function _toEthSignedMessageHash(bytes32 messageHash) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
    }

    function _recoverSigner(bytes32 messageHash, bytes memory signature) internal pure returns (address) {
        if (signature.length != 65) return address(0);
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := mload(add(signature, 0x20))
            s := mload(add(signature, 0x40))
            v := byte(0, mload(add(signature, 0x60)))
        }
        if (uint256(s) > 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0) {
            return address(0);
        }
        if (v < 27) v += 27;
        if (v != 27 && v != 28) return address(0);
        return ecrecover(messageHash, v, r, s);
    }

    function _packValidationData(bool sigFailed, uint48 validUntil, uint48 validAfter) internal pure returns (uint256) {
        return (sigFailed ? 1 : 0) | (uint256(validUntil) << 160) | (uint256(validAfter) << (160 + 48));
    }
}

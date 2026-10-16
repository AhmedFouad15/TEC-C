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
    /// @notice EIP-1271 magic value returned on successful signature validation
    bytes4 internal constant EIP1271_SUCCESS = 0x1626ba7e;
    /// @notice EIP-1271 failure return value
    bytes4 internal constant EIP1271_FAILED = 0xffffffff;

    /**
     * @notice Structure storing registration data for an ephemeral AI session key.
     * @param sessionKey The public address of the authorized session key.
     * @param validAfter Timestamp after which the key becomes active.
     * @param validUntil Timestamp after which the key expires.
     * @param mandateRoot EIP-712 mandate commitment digest (WeIdentity W3C credential).
     * @param isActive Boolean flag indicating if the session key is currently active.
     */
    struct SessionKeyData {
        address sessionKey;
        uint48 validAfter;
        uint48 validUntil;
        bytes32 mandateRoot;
        bool isActive;
    }

    /// @notice Nested mapping storing session key configuration: account => sessionKey => SessionKeyData
    mapping(address => mapping(address => SessionKeyData)) public sessionKeys;

    /**
     * @notice Emitted when a new session key is registered for a smart account.
     * @param account The smart account granting the session authorization.
     * @param sessionKey The ephemeral session key address.
     * @param validAfter Earliest valid execution timestamp.
     * @param validUntil Expiration execution timestamp.
     * @param mandateRoot EIP-712 mandate digest commitment (WeIdentity W3C verifiable credential).
     */
    event SessionKeyRegistered(
        address indexed account, address indexed sessionKey, uint48 validAfter, uint48 validUntil, bytes32 mandateRoot
    );

    /**
     * @notice Emitted when an active session key is explicitly revoked.
     * @param account The smart account revoking authorization.
     * @param sessionKey The revoked session key address.
     */
    event SessionKeyRevoked(address indexed account, address indexed sessionKey);

    /// @notice Reverts if validUntil timestamp is not strictly greater than validAfter.
    error InvalidTimeRange();
    /// @notice Reverts if session key is not currently active.
    error SessionKeyNotActive();
    /// @notice Reverts if current block timestamp is outside the session validity window.
    error SessionKeyExpired();
    /// @notice Reverts if session key address is invalid or zero.
    error InvalidSignature();
    /// @notice Reverts if caller is not the smart account owning the session configuration.
    error UnauthorizedCaller();

    /**
     * @notice Registers an ephemeral session key for a smart account with strict time and mandate bounds.
     * @dev Restricted strictly to the calling smart account (`msg.sender == account`).
     * @param account The smart account address granting authorization.
     * @param sessionKey The public address of the session key to register.
     * @param validAfter Earliest timestamp after which transactions are permitted.
     * @param validUntil Expiration timestamp after which transactions revert.
     * @param mandateRoot EIP-712 mandate commitment digest for WeIdentity W3C anchoring.
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
     * @dev Restricted strictly to the smart account.
     * @param account The smart account address revoking the session key.
     * @param sessionKey The address of the session key to deactivate.
     */
    function revokeSessionKey(address account, address sessionKey) external {
        if (msg.sender != account) revert UnauthorizedCaller();
        sessionKeys[account][sessionKey].isActive = false;
        emit SessionKeyRevoked(account, sessionKey);
    }

    /**
     * @notice Verifies whether a given mandate digest matches the on-chain committed mandateRoot for a session key.
     * @dev Provides cryptographic anchoring for WeIdentity W3C Verifiable Credentials.
     * @param account The smart account address.
     * @param sessionKey The ephemeral session key address.
     * @param mandateDigest EIP-712 mandate digest to verify against on-chain root.
     * @return isValid True if committedRoot is non-zero and equals mandateDigest.
     * @return committedRoot The on-chain root stored for this session key.
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
     * @notice Validates an ERC-4337 PackedUserOperation signed by an ephemeral session key.
     * @dev Slices sessionKey and signature from userOp.signature. Verifies time window and WeIdentity commitment.
     * @param userOp The packed ERC-4337 UserOperation.
     * @param userOpHash Hash of the user operation calculated by EntryPoint.
     * @return validationData Packed validation data (0 for success, 1 for failure, or time range).
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
     * @notice Standard ERC-1271 off-chain signature validation for ephemeral session keys.
     * @param sender The address of the smart account.
     * @param hash The 32-byte hash of the data being verified.
     * @param data Signature payload (sessionKey || ECDSA signature || optional mandate digest).
     * @return Magic value 0x1626ba7e if signature is valid, 0xffffffff otherwise.
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

    /**
     * @dev Prefixes a message hash with "\x19Ethereum Signed Message:\n32" and hashes it.
     * @param messageHash The raw 32-byte message hash.
     * @return Resulting EIP-191 digest.
     */
    function _toEthSignedMessageHash(bytes32 messageHash) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
    }

    /**
     * @dev Recovers signer address from hash and 65-byte ECDSA signature, rejecting malleable signatures.
     * @param messageHash 32-byte digest that was signed.
     * @param signature 65-byte ECDSA signature (r, s, v).
     * @return Recovered signer address (or address(0) if invalid).
     */
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

    /**
     * @dev Packs boolean failure status and validity bounds into standard ERC-4337 validationData format.
     * @param sigFailed True if signature validation failed.
     * @param validUntil Expiration timestamp for the UserOp.
     * @param validAfter Earliest timestamp for the UserOp.
     * @return Packed 256-bit validationData value.
     */
    function _packValidationData(bool sigFailed, uint48 validUntil, uint48 validAfter) internal pure returns (uint256) {
        return (sigFailed ? 1 : 0) | (uint256(validUntil) << 160) | (uint256(validAfter) << (160 + 48));
    }
}

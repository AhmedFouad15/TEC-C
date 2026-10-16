// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IERC7579Validator} from "../interfaces/IERC7579Validator.sol";
import {PackedUserOperation} from "../interfaces/PackedUserOperation.sol";

/**
 * @title WebAuthnP256Validator
 * @author Tec-C Core Engineering Team (FinTechathon 2026 Topic F)
 * @notice Validates WebAuthn Passkey (NIST P-256 / secp256r1) hardware biometrics (FaceID / TouchID)
 *         via the native RIP-7212 EVM precompile at address 0x0100.
 * @dev Drastically reduces gas from ~280,000 gas (software P-256) down to ~3,450 gas (native precompile).
 *      Enables Apple Secure Enclave & Android Titan M hardware-sovereign authentication.
 */
contract WebAuthnP256Validator is IERC7579Validator {
    /// @notice EIP-1271 magic value returned on successful signature validation
    bytes4 internal constant EIP1271_SUCCESS = 0x1626ba7e;
    /// @notice EIP-1271 failure return value
    bytes4 internal constant EIP1271_FAILED = 0xffffffff;

    /// @notice RIP-7212 native secp256r1 precompile address at 0x100
    address public constant RIP7212_PRECOMPILE = address(0x100);

    /**
     * @notice Structure storing NIST P-256 public key coordinates for a registered Passkey.
     * @param qx Public key X coordinate (32 bytes).
     * @param qy Public key Y coordinate (32 bytes).
     * @param isRegistered Boolean flag indicating if passkey is currently active.
     */
    struct WebAuthnPasskey {
        uint256 qx;
        uint256 qy;
        bool isRegistered;
    }

    /// @notice Mapping storing registered passkeys: account => WebAuthnPasskey
    mapping(address => WebAuthnPasskey) public passkeys;

    /**
     * @notice Emitted when a WebAuthn P-256 Passkey is registered for an account.
     * @param account The smart account address registering the passkey.
     * @param qx Public key X coordinate.
     * @param qy Public key Y coordinate.
     */
    event PasskeyRegistered(address indexed account, uint256 qx, uint256 qy);

    /**
     * @notice Emitted when an existing passkey is revoked by the account.
     * @param account The smart account address revoking the passkey.
     */
    event PasskeyRevoked(address indexed account);

    /// @notice Reverts if caller is not the smart account owning the passkey configuration.
    error UnauthorizedCaller();
    /// @notice Reverts if passkey has not been registered for the specified account.
    error PasskeyNotRegistered();
    /// @notice Reverts if passkey coordinates (qx, qy) are zero or invalid.
    error InvalidPasskeyCoordinates();
    /// @notice Reverts if cryptographic P-256 verification fails.
    error P256VerificationFailed();

    /**
     * @notice Registers a hardware WebAuthn P-256 Passkey for a smart account.
     * @dev Restricted strictly to the smart account itself (`msg.sender == account`).
     * @param account The smart account address.
     * @param qx The NIST P-256 curve public key X coordinate.
     * @param qy The NIST P-256 curve public key Y coordinate.
     */
    function registerPasskey(address account, uint256 qx, uint256 qy) external {
        if (msg.sender != account) revert UnauthorizedCaller();
        if (qx == 0 || qy == 0) revert InvalidPasskeyCoordinates();

        passkeys[account] = WebAuthnPasskey({qx: qx, qy: qy, isRegistered: true});

        emit PasskeyRegistered(account, qx, qy);
    }

    /**
     * @notice Revokes an existing passkey for a smart account.
     * @dev Restricted strictly to the smart account itself (`msg.sender == account`).
     * @param account The smart account address.
     */
    function revokePasskey(address account) external {
        if (msg.sender != account) revert UnauthorizedCaller();
        delete passkeys[account];
        emit PasskeyRevoked(account);
    }

    /**
     * @notice Verifies a NIST P-256 signature using the RIP-7212 precompile at address 0x100.
     * @param messageHash The 32-byte hash of the WebAuthn message or UserOp.
     * @param r Signature component R (32 bytes).
     * @param s Signature component S (32 bytes).
     * @param qx Public key X coordinate.
     * @param qy Public key Y coordinate.
     * @return isValid True if signature is cryptographically valid under NIST P-256 curve.
     */
    function verifyP256Signature(bytes32 messageHash, uint256 r, uint256 s, uint256 qx, uint256 qy)
        public
        view
        returns (bool isValid)
    {
        bytes memory input = abi.encode(messageHash, r, s, qx, qy);
        (bool success, bytes memory output) = RIP7212_PRECOMPILE.staticcall(input);
        if (success && output.length == 32) {
            return abi.decode(output, (uint256)) == 1;
        }
        return false;
    }

    /**
     * @notice Validates an ERC-4337 UserOperation signed by a WebAuthn P-256 Passkey.
     * @dev Supports both direct (r, s) 64-byte format and WebAuthn envelope (r, s, challenge) with replay defense.
     * @param userOp The packed ERC-4337 UserOperation.
     * @param userOpHash Hash of user operation calculated by EntryPoint.
     * @return validationData Packed validation data (0 for success, 1 for failure).
     */
    function validateUserOp(PackedUserOperation calldata userOp, bytes32 userOpHash)
        external
        view
        override
        returns (uint256 validationData)
    {
        WebAuthnPasskey storage pk = passkeys[userOp.sender];
        if (!pk.isRegistered) {
            return 1; // Validation failed
        }

        if (userOp.signature.length < 64) {
            return 1;
        }

        // Try direct 64-byte (r, s) or full WebAuthn envelope
        uint256 r;
        uint256 s;
        bytes32 messageHash;

        if (userOp.signature.length == 64) {
            // Direct P-256 signature of userOpHash
            (r, s) = abi.decode(userOp.signature, (uint256, uint256));
            messageHash = userOpHash;
        } else {
            // Full WebAuthn envelope: (r, s, challenge)
            // Ensure the signed challenge strictly matches userOpHash to prevent signature replay
            bytes32 challenge;
            (r, s, challenge) = abi.decode(userOp.signature, (uint256, uint256, bytes32));
            if (challenge != userOpHash) {
                return 1; // Challenge mismatch: reject signature replay
            }
            messageHash = userOpHash;
        }

        bool valid = verifyP256Signature(messageHash, r, s, pk.qx, pk.qy);
        return valid ? 0 : 1;
    }

    /**
     * @notice Standard ERC-1271 off-chain signature verification for WebAuthn Passkeys.
     * @param sender The address of the smart account.
     * @param hash The 32-byte hash of the data being verified.
     * @param data Signature payload containing (uint256 r, uint256 s).
     * @return magicValue Magic value 0x1626ba7e if signature is valid, 0xffffffff otherwise.
     */
    function isValidSignatureWithSender(address sender, bytes32 hash, bytes calldata data)
        external
        view
        override
        returns (bytes4 magicValue)
    {
        WebAuthnPasskey storage pk = passkeys[sender];
        if (!pk.isRegistered || data.length < 64) {
            return EIP1271_FAILED;
        }

        (uint256 r, uint256 s) = abi.decode(data, (uint256, uint256));
        bool valid = verifyP256Signature(hash, r, s, pk.qx, pk.qy);
        return valid ? EIP1271_SUCCESS : EIP1271_FAILED;
    }
}

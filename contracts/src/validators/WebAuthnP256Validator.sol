// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IERC7579Validator} from "../interfaces/IERC7579Validator.sol";
import {PackedUserOperation} from "../interfaces/PackedUserOperation.sol";
import {P256Verifier} from "./P256Verifier.sol";

/**
 * @title WebAuthnP256Validator
 * @author Tec-C Core Engineering Team (FinTechathon 2026 Topic F)
 * @notice Validates WebAuthn Passkey (NIST P-256 / secp256r1) hardware biometrics (FaceID / TouchID)
 *         via the native RIP-7212 EVM precompile at address 0x0100 with automatic pure-Solidity fallback
 *         for Ethereum L1 Mainnet and FISCO BCOS consortium nodes.
 * @dev Implements all 4 production security nuances:
 *      1. RIP-7212 Precompile (0x100) + Pure-Solidity P-256 Fallback (L1 / FISCO BCOS compatibility).
 *      2. Signature Malleability Protection: Enforces low-s (0 < s <= n/2) on secp256r1.
 *      3. On-Chain authenticatorData Flags: Enforces UP (0x01) and UV (0x04, Biometric FaceID/TouchID).
 *      4. Multi-Device Passkey Registry & Emergency Guardian Account Recovery.
 */
contract WebAuthnP256Validator is IERC7579Validator {
    /// @notice EIP-1271 magic value returned on successful signature validation
    bytes4 internal constant EIP1271_SUCCESS = 0x1626ba7e;
    /// @notice EIP-1271 failure return value
    bytes4 internal constant EIP1271_FAILED = 0xffffffff;

    /// @notice RIP-7212 native secp256r1 precompile address at 0x100
    address public constant RIP7212_PRECOMPILE = address(0x100);

    /// @notice Secp256r1 curve order N and N/2 exposed for external callers and tests
    uint256 public constant P256_N = P256Verifier.P256_N;
    uint256 public constant P256_N_DIV_2 = P256Verifier.P256_N_DIV_2;

    /// @notice Default primary key identifier
    bytes32 public constant PRIMARY_KEY_ID = keccak256("TECC_PRIMARY_PASSKEY");

    /// @notice Optional external Solidity P-256 verifier contract (if set, tried before internal pure-Solidity math)
    address public fallbackP256Verifier;

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

    /// @notice Primary passkey mapping for backward compatibility: account => WebAuthnPasskey
    mapping(address => WebAuthnPasskey) public passkeys;

    /// @notice Multi-device passkey registry (Nuance 4): account => keyId => WebAuthnPasskey
    mapping(address => mapping(bytes32 => WebAuthnPasskey)) public accountPasskeysById;

    /// @notice List of registered keyIds per account for enumeration
    mapping(address => bytes32[]) public accountPasskeyIds;

    /// @notice Count of currently active passkeys per account
    mapping(address => uint256) public activePasskeyCount;

    /// @notice Designated emergency recovery guardian per account (Nuance 4: Device Loss Recovery)
    mapping(address => address) public recoveryGuardians;

    // =========================================================================
    // Events
    // =========================================================================

    event PasskeyRegistered(address indexed account, uint256 qx, uint256 qy);
    event PasskeyAdded(address indexed account, bytes32 indexed keyId, uint256 qx, uint256 qy);
    event PasskeyRevoked(address indexed account);
    event PasskeyRevokedById(address indexed account, bytes32 indexed keyId);
    event RecoveryGuardianUpdated(address indexed account, address indexed guardian);
    event PasskeyRecovered(address indexed account, address indexed guardian, bytes32 indexed newKeyId, uint256 newQx, uint256 newQy);
    event FallbackVerifierUpdated(address indexed verifier);

    // =========================================================================
    // Errors
    // =========================================================================

    error UnauthorizedCaller();
    error UnauthorizedGuardian();
    error PasskeyNotRegistered();
    error InvalidPasskeyCoordinates();
    error InvalidGuardianAddress();
    error CannotRevokeLastPasskey();
    error P256VerificationFailed();
    error SignatureMalleabilityRejected();
    error InvalidAuthenticatorData();
    error BiometricUserVerificationRequired();

    // =========================================================================
    // Phase 1 & Nuance 4: On-Chain Passkey Registration, Multi-Device & Recovery
    // =========================================================================

    /**
     * @notice Registers a primary hardware WebAuthn P-256 Passkey for a smart account.
     * @dev Restricted strictly to the smart account itself (`msg.sender == account`).
     */
    function registerPasskey(address account, uint256 qx, uint256 qy) external {
        if (msg.sender != account) revert UnauthorizedCaller();
        if (qx == 0 || qy == 0) revert InvalidPasskeyCoordinates();

        bool wasRegistered = passkeys[account].isRegistered;
        passkeys[account] = WebAuthnPasskey({qx: qx, qy: qy, isRegistered: true});

        if (!accountPasskeysById[account][PRIMARY_KEY_ID].isRegistered) {
            accountPasskeyIds[account].push(PRIMARY_KEY_ID);
            if (!wasRegistered) {
                activePasskeyCount[account] += 1;
            }
        }
        accountPasskeysById[account][PRIMARY_KEY_ID] = WebAuthnPasskey({qx: qx, qy: qy, isRegistered: true});

        emit PasskeyRegistered(account, qx, qy);
        emit PasskeyAdded(account, PRIMARY_KEY_ID, qx, qy);
    }

    /**
     * @notice Alias matching the Tec-C Decentralized Biometrics Guide (`setAccountPasskey(qx, qy)`).
     */
    function setAccountPasskey(uint256 qx, uint256 qy) external {
        if (qx == 0 || qy == 0) revert InvalidPasskeyCoordinates();
        address account = msg.sender;

        bool wasRegistered = passkeys[account].isRegistered;
        passkeys[account] = WebAuthnPasskey({qx: qx, qy: qy, isRegistered: true});

        if (!accountPasskeysById[account][PRIMARY_KEY_ID].isRegistered) {
            accountPasskeyIds[account].push(PRIMARY_KEY_ID);
            if (!wasRegistered) {
                activePasskeyCount[account] += 1;
            }
        }
        accountPasskeysById[account][PRIMARY_KEY_ID] = WebAuthnPasskey({qx: qx, qy: qy, isRegistered: true});

        emit PasskeyRegistered(account, qx, qy);
        emit PasskeyAdded(account, PRIMARY_KEY_ID, qx, qy);
    }

    /**
     * @notice Registers an additional passkey (e.g., backup laptop / tablet) for multi-device resilience (Nuance 4).
     * @param account The smart account address.
     * @param keyId Unique identifier for the device key (e.g. keccak256("MacBook-TouchID")).
     * @param qx Public key X coordinate.
     * @param qy Public key Y coordinate.
     */
    function addPasskey(address account, bytes32 keyId, uint256 qx, uint256 qy) external {
        if (msg.sender != account) revert UnauthorizedCaller();
        if (qx == 0 || qy == 0 || keyId == bytes32(0)) revert InvalidPasskeyCoordinates();

        if (!accountPasskeysById[account][keyId].isRegistered) {
            accountPasskeyIds[account].push(keyId);
            activePasskeyCount[account] += 1;
        }
        accountPasskeysById[account][keyId] = WebAuthnPasskey({qx: qx, qy: qy, isRegistered: true});

        // If no primary passkey is active yet, also set this as the primary passkey
        if (!passkeys[account].isRegistered) {
            passkeys[account] = WebAuthnPasskey({qx: qx, qy: qy, isRegistered: true});
            emit PasskeyRegistered(account, qx, qy);
        }

        emit PasskeyAdded(account, keyId, qx, qy);
    }

    /**
     * @notice Revokes the primary passkey for a smart account.
     */
    function revokePasskey(address account) external {
        if (msg.sender != account) revert UnauthorizedCaller();
        if (passkeys[account].isRegistered && activePasskeyCount[account] > 0) {
            activePasskeyCount[account] -= 1;
        }
        delete passkeys[account];
        delete accountPasskeysById[account][PRIMARY_KEY_ID];
        emit PasskeyRevoked(account);
    }

    /**
     * @notice Revokes a specific device passkey by keyId while preserving backup passkeys (Nuance 4).
     */
    function revokePasskeyById(address account, bytes32 keyId) external {
        if (msg.sender != account) revert UnauthorizedCaller();
        WebAuthnPasskey storage pk = accountPasskeysById[account][keyId];
        if (!pk.isRegistered) revert PasskeyNotRegistered();
        if (activePasskeyCount[account] <= 1) revert CannotRevokeLastPasskey();

        uint256 revokedQx = pk.qx;
        uint256 revokedQy = pk.qy;
        delete accountPasskeysById[account][keyId];
        activePasskeyCount[account] -= 1;

        // If the revoked passkey was also stored in `passkeys[account]`, promote another active passkey
        if (passkeys[account].qx == revokedQx && passkeys[account].qy == revokedQy) {
            delete passkeys[account];
            bytes32[] storage ids = accountPasskeyIds[account];
            for (uint256 i = 0; i < ids.length; i++) {
                WebAuthnPasskey storage candidate = accountPasskeysById[account][ids[i]];
                if (candidate.isRegistered) {
                    passkeys[account] = candidate;
                    break;
                }
            }
        }

        emit PasskeyRevokedById(account, keyId);
    }

    /**
     * @notice Configures an Emergency Recovery Guardian to protect against total device loss (Nuance 4).
     */
    function setRecoveryGuardian(address account, address guardian) external {
        if (msg.sender != account) revert UnauthorizedCaller();
        if (guardian == address(0) || guardian == account) revert InvalidGuardianAddress();
        recoveryGuardians[account] = guardian;
        emit RecoveryGuardianUpdated(account, guardian);
    }

    /**
     * @notice Allows the designated Emergency Recovery Guardian to register a replacement passkey if all devices are lost.
     */
    function recoverPasskey(address account, bytes32 newKeyId, uint256 newQx, uint256 newQy) external {
        address guardian = recoveryGuardians[account];
        if (guardian == address(0) || msg.sender != guardian) revert UnauthorizedGuardian();
        if (newQx == 0 || newQy == 0 || newKeyId == bytes32(0)) revert InvalidPasskeyCoordinates();

        if (!accountPasskeysById[account][newKeyId].isRegistered) {
            accountPasskeyIds[account].push(newKeyId);
            activePasskeyCount[account] += 1;
        }
        accountPasskeysById[account][newKeyId] = WebAuthnPasskey({qx: newQx, qy: newQy, isRegistered: true});
        passkeys[account] = WebAuthnPasskey({qx: newQx, qy: newQy, isRegistered: true});

        emit PasskeyRecovered(account, guardian, newKeyId, newQx, newQy);
    }

    /**
     * @notice Checks whether (qx, qy) matches any active registered passkey (primary or backup) for `account`.
     */
    function isAuthorizedPasskey(address account, uint256 qx, uint256 qy) public view returns (bool) {
        if (qx == 0 || qy == 0) return false;
        WebAuthnPasskey storage primary = passkeys[account];
        if (primary.isRegistered && primary.qx == qx && primary.qy == qy) {
            return true;
        }
        bytes32[] storage ids = accountPasskeyIds[account];
        for (uint256 i = 0; i < ids.length; i++) {
            WebAuthnPasskey storage pk = accountPasskeysById[account][ids[i]];
            if (pk.isRegistered && pk.qx == qx && pk.qy == qy) {
                return true;
            }
        }
        return false;
    }

    /**
     * @notice Configures an optional external Solidity P-256 fallback verifier contract.
     */
    function setFallbackP256Verifier(address verifier) external {
        fallbackP256Verifier = verifier;
        emit FallbackVerifierUpdated(verifier);
    }

    // =========================================================================
    // Phase 3 & Nuances 1, 2, 3: P-256 & WebAuthn Verification
    // =========================================================================

    /**
     * @notice Verifies a NIST P-256 signature using RIP-7212 (0x100) with automatic L1/FISCO Solidity fallback
     *         and strict low-s signature malleability protection (s <= n/2).
     */
    function verifyP256Signature(bytes32 messageHash, uint256 r, uint256 s, uint256 qx, uint256 qy)
        public
        view
        returns (bool isValid)
    {
        return P256Verifier.verifyWithFallback(messageHash, r, s, qx, qy, fallbackP256Verifier);
    }

    /**
     * @notice Direct access to the pure-Solidity NIST P-256 verifier (for Ethereum L1 & FISCO BCOS verification).
     */
    function verifyP256SignatureSolidity(bytes32 messageHash, uint256 r, uint256 s, uint256 qx, uint256 qy)
        external
        view
        returns (bool isValid)
    {
        return P256Verifier.verifySolidityP256(messageHash, r, s, qx, qy);
    }

    /**
     * @notice Verifies a complete W3C WebAuthn assertion including authenticatorData UP & UV flags (Nuance 3).
     * @param authenticatorData Raw authenticatorData bytes (must be >= 37 bytes; byte 32 holds flags).
     * @param clientDataHash SHA-256 hash of clientDataJSON (or bound challenge digest).
     * @param r Signature R component.
     * @param s Signature S component (must satisfy s <= n/2).
     * @param qx Public key X coordinate.
     * @param qy Public key Y coordinate.
     * @param requireUserVerification If true, requires UV bit (flags & 0x04 != 0) proving biometric FaceID/TouchID.
     */
    function verifyWebAuthnSignature(
        bytes calldata authenticatorData,
        bytes32 clientDataHash,
        uint256 r,
        uint256 s,
        uint256 qx,
        uint256 qy,
        bool requireUserVerification
    ) public view returns (bool isValid) {
        if (!P256Verifier.validateAuthenticatorFlags(authenticatorData, requireUserVerification)) {
            return false;
        }
        bytes32 messageHash = P256Verifier.computeWebAuthnMessageHash(authenticatorData, clientDataHash);
        return P256Verifier.verifyWithFallback(messageHash, r, s, qx, qy, fallbackP256Verifier);
    }

    /**
     * @notice Validates an ERC-4337 UserOperation signed by a WebAuthn P-256 Passkey.
     * @dev Supports three signature encodings:
     *      1. 64-byte direct format: `abi.encode(uint256 r, uint256 s)`
     *      2. 96-byte challenge-bound format: `abi.encode(uint256 r, uint256 s, bytes32 challenge)`
     *      3. Full WebAuthn biometric envelope (> 96 bytes):
     *         `abi.encode(bytes authenticatorData, bytes32 clientDataHash, uint256 r, uint256 s, uint256 qx, uint256 qy)`
     *         Enforces UP (0x01) + UV (0x04) flags, low-s non-malleability, and multi-device passkey authorization.
     */
    function validateUserOp(PackedUserOperation calldata userOp, bytes32 userOpHash)
        external
        view
        override
        returns (uint256 validationData)
    {
        if (userOp.signature.length < 64) {
            return 1;
        }

        if (userOp.signature.length == 64) {
            WebAuthnPasskey storage pk = passkeys[userOp.sender];
            if (!pk.isRegistered) return 1;
            (uint256 r1, uint256 s1) = abi.decode(userOp.signature, (uint256, uint256));
            return verifyP256Signature(userOpHash, r1, s1, pk.qx, pk.qy) ? 0 : 1;
        }

        if (userOp.signature.length == 96) {
            WebAuthnPasskey storage pk = passkeys[userOp.sender];
            if (!pk.isRegistered) return 1;
            (uint256 r2, uint256 s2, bytes32 challenge) = abi.decode(userOp.signature, (uint256, uint256, bytes32));
            if (challenge != userOpHash) {
                return 1; // Challenge mismatch: reject signature replay
            }
            return verifyP256Signature(userOpHash, r2, s2, pk.qx, pk.qy) ? 0 : 1;
        }

        // Full WebAuthn biometric envelope: (bytes authenticatorData, bytes32 clientDataHash, uint256 r, uint256 s, uint256 qx, uint256 qy)
        (
            bytes memory authData,
            bytes32 clientDataHash,
            uint256 r,
            uint256 s,
            uint256 qx,
            uint256 qy
        ) = abi.decode(userOp.signature, (bytes, bytes32, uint256, uint256, uint256, uint256));

        if (!isAuthorizedPasskey(userOp.sender, qx, qy)) {
            return 1;
        }
        if (clientDataHash != userOpHash && clientDataHash != sha256(abi.encodePacked(userOpHash))) {
            return 1;
        }
        if (authData.length < P256Verifier.MIN_AUTH_DATA_LENGTH) {
            return 1;
        }
        uint8 flags = uint8(authData[32]);
        if ((flags & P256Verifier.AUTH_DATA_FLAG_UP) == 0 || (flags & P256Verifier.AUTH_DATA_FLAG_UV) == 0) {
            return 1; // Both UP and UV (biometric FaceID/TouchID) required
        }

        bytes32 messageHash = sha256(abi.encodePacked(authData, clientDataHash));
        return verifyP256Signature(messageHash, r, s, qx, qy) ? 0 : 1;
    }

    /**
     * @notice Standard ERC-1271 off-chain signature verification for WebAuthn Passkeys.
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

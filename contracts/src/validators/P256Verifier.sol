// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title P256Verifier
 * @author Tec-C Core Engineering Team
 * @notice Bulletproof NIST P-256 (secp256r1) signature verification library & fallback contract.
 * @dev Implements the 4 production technical nuances for decentralized WebAuthn Passkeys:
 *      1. Dual-Path Verification: Queries native RIP-7212 precompile at 0x100 first (~3,450-9,964 gas on Arbitrum L2);
 *         if 0x100 is unavailable (e.g. Ethereum L1 Mainnet or FISCO BCOS without 0x100), routes to an optional
 *         external verifier contract or executes pure-Solidity Jacobian secp256r1 verification via EIP-198 modexp (0x05).
 *      2. Strict Low-S Signature Malleability Defense: Enforces 0 < s <= N / 2 on secp256r1.
 *      3. On-Chain WebAuthn authenticatorData Flag Verification: Enforces UP (0x01) and UV (0x04, Biometric FaceID/TouchID).
 */
library P256Verifier {
    /// @notice Native RIP-7212 secp256r1 precompile address (active on Arbitrum One, Optimism, Base, Polygon)
    address internal constant RIP7212_PRECOMPILE = address(0x0100);

    /// @notice Standard EIP-198 BigInt modular exponentiation precompile (active on Ethereum L1, L2s, and FISCO BCOS)
    address internal constant MODEXP_PRECOMPILE = address(0x0005);

    // =========================================================================
    // NIST P-256 (secp256r1) Elliptic Curve Constants
    // =========================================================================

    /// @notice Prime field modulus p = 2^256 - 2^224 + 2^192 + 2^96 - 1
    uint256 internal constant P256_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF;

    /// @notice Curve parameter a = p - 3
    uint256 internal constant P256_A = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFC;

    /// @notice Curve parameter b
    uint256 internal constant P256_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B;

    /// @notice Curve group order n
    uint256 internal constant P256_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551;

    /// @notice Half curve order n / 2 for strict low-s malleability check (Nuance 2)
    uint256 internal constant P256_N_DIV_2 = 0x7FFFFFFF800000007FFFFFFFFFFFFFFFDE737D56D38BCE4279DCB5617E3192A8;

    /// @notice Generator point G affine X coordinate
    uint256 internal constant P256_GX = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296;

    /// @notice Generator point G affine Y coordinate
    uint256 internal constant P256_GY = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5;

    // =========================================================================
    // WebAuthn AuthenticatorData Bit Flags (Nuance 3)
    // =========================================================================

    /// @notice Bit 0: User Present (UP) - user interacted with the authenticator
    uint8 internal constant AUTH_DATA_FLAG_UP = 0x01;

    /// @notice Bit 2: User Verified (UV) - user biometrically verified via FaceID / TouchID / Passkey PIN
    uint8 internal constant AUTH_DATA_FLAG_UV = 0x04;

    /// @notice Minimum byte length of WebAuthn authenticatorData (32-byte rpIdHash + 1-byte flags + 4-byte signCount)
    uint256 internal constant MIN_AUTH_DATA_LENGTH = 37;

    /**
     * @notice Checks whether (r, s) satisfies strict NIST P-256 range and low-s non-malleability (Nuance 2).
     * @param r Signature R component.
     * @param s Signature S component.
     * @return True if 0 < r < n and 0 < s <= n/2.
     */
    function isCanonicalLowS(uint256 r, uint256 s) internal pure returns (bool) {
        return r > 0 && r < P256_N && s > 0 && s <= P256_N_DIV_2;
    }

    /**
     * @notice Checks whether affine coordinates (qx, qy) lie on the NIST P-256 curve: y^2 == x^3 + ax + b (mod p).
     */
    function isOnCurve(uint256 qx, uint256 qy) internal pure returns (bool) {
        if (qx == 0 || qx >= P256_P || qy == 0 || qy >= P256_P) {
            return false;
        }
        uint256 lhs = mulmod(qy, qy, P256_P);
        uint256 x3 = mulmod(mulmod(qx, qx, P256_P), qx, P256_P);
        uint256 ax = mulmod(P256_A, qx, P256_P);
        uint256 rhs = addmod(addmod(x3, ax, P256_P), P256_B, P256_P);
        return lhs == rhs;
    }

    /**
     * @notice Validates WebAuthn authenticatorData flags (Nuance 3).
     * @param authenticatorData Raw authenticatorData bytes from navigator.credentials.get().
     * @param requireUserVerification If true, enforces Bit 2 (UV = 0x04) in addition to Bit 0 (UP = 0x01).
     * @return valid True if authenticatorData meets length and flag requirements.
     */
    function validateAuthenticatorFlags(bytes calldata authenticatorData, bool requireUserVerification)
        internal
        pure
        returns (bool valid)
    {
        if (authenticatorData.length < MIN_AUTH_DATA_LENGTH) {
            return false;
        }
        uint8 flags = uint8(authenticatorData[32]);
        if ((flags & AUTH_DATA_FLAG_UP) == 0) {
            return false;
        }
        if (requireUserVerification && (flags & AUTH_DATA_FLAG_UV) == 0) {
            return false;
        }
        return true;
    }

    /**
     * @notice Computes the canonical W3C WebAuthn signing digest: sha256(authenticatorData || clientDataHash).
     */
    function computeWebAuthnMessageHash(bytes calldata authenticatorData, bytes32 clientDataHash)
        internal
        pure
        returns (bytes32)
    {
        return sha256(abi.encodePacked(authenticatorData, clientDataHash));
    }

    /**
     * @notice Verifies a NIST P-256 signature with automatic fallback across L2, L1, and FISCO BCOS (Nuances 1 & 2).
     * @dev 1. Enforces strict low-s malleability check (s <= n/2).
     *      2. Calls RIP-7212 precompile at 0x100 if available.
     *      3. If 0x100 returns empty/fails (Ethereum L1 or FISCO BCOS without 0x100), routes to `fallbackVerifier`
     *         if configured, or executes the built-in pure-Solidity Jacobian P-256 verifier.
     */
    function verifyWithFallback(
        bytes32 messageHash,
        uint256 r,
        uint256 s,
        uint256 qx,
        uint256 qy,
        address fallbackVerifier
    ) internal view returns (bool) {
        if (!isCanonicalLowS(r, s)) {
            return false;
        }
        if (qx == 0 || qy == 0) {
            return false;
        }

        bytes memory input = abi.encode(messageHash, r, s, qx, qy);

        // Step 1: Try native RIP-7212 precompile at 0x100 (Arbitrum One, Optimism, Base, Polygon)
        (bool success, bytes memory output) = RIP7212_PRECOMPILE.staticcall(input);
        if (success && output.length == 32) {
            return abi.decode(output, (uint256)) == 1;
        }

        // Step 2: If an external Solidity P-256 verifier contract (e.g. Daimo P256Verifier) is configured, call it
        if (fallbackVerifier != address(0) && fallbackVerifier.code.length > 0) {
            (bool fbSuccess, bytes memory fbOutput) = fallbackVerifier.staticcall(input);
            if (fbSuccess && fbOutput.length == 32) {
                return abi.decode(fbOutput, (uint256)) == 1;
            }
        }

        // Step 3: Pure-Solidity NIST P-256 verification fallback (Ethereum L1 Mainnet & FISCO BCOS)
        return verifySolidityP256(messageHash, r, s, qx, qy);
    }

    /**
     * @notice Pure-Solidity NIST P-256 ECDSA verification using Jacobian coordinates and Shamir's trick.
     * @dev Used automatically when RIP-7212 (0x100) is not deployed on the host chain (e.g., Ethereum L1).
     */
    function verifySolidityP256(bytes32 messageHash, uint256 r, uint256 s, uint256 qx, uint256 qy)
        internal
        view
        returns (bool)
    {
        if (!isCanonicalLowS(r, s) || !isOnCurve(qx, qy)) {
            return false;
        }

        uint256 e = uint256(messageHash);
        uint256 sInv = _modInv(s, P256_N);
        if (sInv == 0) {
            return false;
        }

        uint256 u1 = mulmod(e, sInv, P256_N);
        uint256 u2 = mulmod(r, sInv, P256_N);

        (uint256 rx, , uint256 rz) = _shamirLinearCombination(u1, u2, qx, qy);
        if (rz == 0) {
            return false;
        }

        uint256 z2 = mulmod(rz, rz, P256_P);
        uint256 z2Inv = _modInv(z2, P256_P);
        uint256 affineX = mulmod(rx, z2Inv, P256_P);

        return (affineX % P256_N) == r;
    }

    // =========================================================================
    // Internal Jacobian Elliptic Curve Arithmetic (secp256r1)
    // =========================================================================

    struct JPoint {
        uint256 x;
        uint256 y;
        uint256 z;
    }

    function _subModP(uint256 a, uint256 b) private pure returns (uint256) {
        return addmod(a, P256_P - (b % P256_P), P256_P);
    }

    function _modInv(uint256 x, uint256 m) private view returns (uint256 result) {
        if (x == 0 || x >= m) {
            return 0;
        }
        bytes memory input = abi.encode(uint256(32), uint256(32), uint256(32), x, m - 2, m);
        (bool ok, bytes memory out) = MODEXP_PRECOMPILE.staticcall(input);
        if (ok && out.length == 32) {
            result = abi.decode(out, (uint256));
        }
    }

    function _jDouble(JPoint memory p) private pure returns (JPoint memory r) {
        if (p.y == 0 || p.z == 0) {
            return JPoint(0, 0, 0);
        }
        uint256 yy = mulmod(p.y, p.y, P256_P);
        uint256 yyyy = mulmod(yy, yy, P256_P);
        uint256 zz = mulmod(p.z, p.z, P256_P);
        uint256 s = mulmod(4, mulmod(p.x, yy, P256_P), P256_P);
        uint256 m = mulmod(3, mulmod(_subModP(p.x, zz), addmod(p.x, zz, P256_P), P256_P), P256_P);

        r.x = _subModP(mulmod(m, m, P256_P), addmod(s, s, P256_P));
        r.y = _subModP(mulmod(m, _subModP(s, r.x), P256_P), mulmod(8, yyyy, P256_P));
        r.z = mulmod(2, mulmod(p.y, p.z, P256_P), P256_P);
    }

    function _jAdd(JPoint memory p1, JPoint memory p2) private pure returns (JPoint memory r) {
        if (p1.z == 0) {
            return p2;
        }
        if (p2.z == 0) {
            return p1;
        }

        uint256 u1 = mulmod(p1.x, mulmod(p2.z, p2.z, P256_P), P256_P);
        uint256 h = mulmod(p2.x, mulmod(p1.z, p1.z, P256_P), P256_P);
        uint256 s1 = mulmod(p1.y, mulmod(p2.z, mulmod(p2.z, p2.z, P256_P), P256_P), P256_P);
        uint256 rr = mulmod(p2.y, mulmod(p1.z, mulmod(p1.z, p1.z, P256_P), P256_P), P256_P);

        if (u1 == h) {
            if (s1 != rr) {
                return JPoint(0, 0, 0);
            }
            return _jDouble(p1);
        }

        h = _subModP(h, u1);
        rr = _subModP(rr, s1);
        r.z = mulmod(h, mulmod(p1.z, p2.z, P256_P), P256_P);

        uint256 hhh = mulmod(h, mulmod(h, h, P256_P), P256_P);
        u1 = mulmod(u1, mulmod(h, h, P256_P), P256_P);

        r.x = _subModP(_subModP(mulmod(rr, rr, P256_P), hhh), addmod(u1, u1, P256_P));
        r.y = _subModP(mulmod(rr, _subModP(u1, r.x), P256_P), mulmod(s1, hhh, P256_P));
    }

    function _shamirLinearCombination(uint256 u1, uint256 u2, uint256 qx, uint256 qy)
        private
        pure
        returns (uint256 rx, uint256 ry, uint256 rz)
    {
        JPoint memory g = JPoint(P256_GX, P256_GY, 1);
        JPoint memory q = JPoint(qx, qy, 1);
        JPoint memory gq = _jAdd(g, q);
        JPoint memory acc = JPoint(0, 0, 0);

        for (uint256 i = 256; i > 0;) {
            unchecked {
                --i;
            }
            acc = _jDouble(acc);
            bool b1 = ((u1 >> i) & 1) == 1;
            bool b2 = ((u2 >> i) & 1) == 1;
            if (b1 && b2) {
                acc = _jAdd(acc, gq);
            } else if (b1) {
                acc = _jAdd(acc, g);
            } else if (b2) {
                acc = _jAdd(acc, q);
            }
        }
        return (acc.x, acc.y, acc.z);
    }
}

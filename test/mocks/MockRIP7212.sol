// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title MockRIP7212
 * @notice Mock implementation of the native RIP-7212 P-256 precompile at 0x100 for testing.
 */
contract MockRIP7212 {
    fallback(bytes calldata input) external returns (bytes memory) {
        if (input.length != 160) {
            return abi.encode(uint256(0));
        }

        (bytes32 messageHash, uint256 r, uint256 s, uint256 qx, uint256 qy) = abi.decode(
            input,
            (bytes32, uint256, uint256, uint256, uint256)
        );

        // Treat r == 0xDEAD as intentional failure for negative testing
        if (r == 0xDEAD || s == 0xDEAD || qx == 0 || qy == 0 || messageHash == bytes32(0)) {
            return abi.encode(uint256(0));
        }

        return abi.encode(uint256(1));
    }
}

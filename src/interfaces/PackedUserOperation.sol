// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title PackedUserOperation
 * @notice Standard ERC-4337 v0.7 UserOperation struct.
 */
struct PackedUserOperation {
    address sender;
    uint256 nonce;
    bytes initCode;
    bytes callData;
    bytes32 accountGasLimits;
    uint256 preVerificationGas;
    bytes32 gasFees;
    bytes paymasterAndData;
    bytes signature;
}

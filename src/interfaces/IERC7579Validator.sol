// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {PackedUserOperation} from "./PackedUserOperation.sol";

/**
 * @title IERC7579Validator
 * @notice Standard interface for ERC-7579 validation modules.
 */
interface IERC7579Validator {
    /**
     * @notice Validates an ERC-4337 PackedUserOperation.
     * @param userOp The packed user operation.
     * @param userOpHash The hash of the user operation calculated by EntryPoint.
     * @return validationData Packed validation status (authorizer, validUntil, validAfter).
     */
    function validateUserOp(PackedUserOperation calldata userOp, bytes32 userOpHash)
        external
        returns (uint256 validationData);

    /**
     * @notice Standard ERC-1271 / ERC-7579 signature validation for 6492 / ECDSA.
     * @param sender The address of the smart account.
     * @param hash The data hash being signed.
     * @param data The signature payload.
     * @return magicValue EIP-1271 magic value (0x1626ba7e) if valid.
     */
    function isValidSignatureWithSender(address sender, bytes32 hash, bytes calldata data)
        external
        view
        returns (bytes4 magicValue);
}

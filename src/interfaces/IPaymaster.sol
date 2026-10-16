// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {PackedUserOperation} from "./PackedUserOperation.sol";

/**
 * @title IPaymaster
 * @notice Standard ERC-4337 v0.7 Paymaster interface.
 */
interface IPaymaster {
    enum PostOpMode {
        opSucceeded,
        opReverted,
        postOpReverted
    }

    /**
     * @notice Validates whether the paymaster agrees to sponsor the user operation.
     * @param userOp The packed user operation.
     * @param userOpHash Hash of the user operation.
     * @param maxCost Maximum gas cost that the account or paymaster will be required to pay.
     * @return context Context to pass to postOp.
     * @return validationData Packed validation status (authorizer, validUntil, validAfter).
     */
    function validatePaymasterUserOp(PackedUserOperation calldata userOp, bytes32 userOpHash, uint256 maxCost)
        external
        returns (bytes memory context, uint256 validationData);

    /**
     * @notice Post-operation callback for charge tracking and accounting.
     * @param mode Post-operation execution status.
     * @param context Context returned by validatePaymasterUserOp.
     * @param actualGasCost Actual gas cost incurred by the operation.
     * @param actualUserOpFeePerGas Actual fee per gas paid by the operation.
     */
    function postOp(PostOpMode mode, bytes calldata context, uint256 actualGasCost, uint256 actualUserOpFeePerGas)
        external;
}

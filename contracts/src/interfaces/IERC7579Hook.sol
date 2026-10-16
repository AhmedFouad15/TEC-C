// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title IERC7579Hook
 * @notice Standard interface for ERC-7579 Execution Hooks.
 * @dev Hooks enforce pre-execution invariant verification and post-execution audit logging.
 */
interface IERC7579Hook {
    /**
     * @notice Called immediately before execution by the modular smart account.
     * @param msgSender The original sender initiating the execution.
     * @param value The native token value being transmitted.
     * @param msgData The execution payload.
     * @return hookData Contextual state passed to postCheck.
     */
    function preCheck(address msgSender, uint256 value, bytes calldata msgData) external returns (bytes memory hookData);

    /**
     * @notice Called immediately after execution by the modular smart account.
     * @param hookData Contextual state passed from preCheck.
     */
    function postCheck(bytes calldata hookData) external;
}

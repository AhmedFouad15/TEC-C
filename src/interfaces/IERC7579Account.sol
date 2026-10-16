// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

// Module type identifiers defined by ERC-7579
uint256 constant MODULE_TYPE_VALIDATOR = 1;
uint256 constant MODULE_TYPE_EXECUTOR = 2;
uint256 constant MODULE_TYPE_FALLBACK = 3;
uint256 constant MODULE_TYPE_HOOK = 4;

/**
 * @title Execution
 * @dev Struct representing a single on-chain execution target, value, and callData.
 */
struct Execution {
    address target;
    uint256 value;
    bytes callData;
}

/**
 * @title IERC7579Account
 * @notice Standard interface for ERC-7579 Modular Smart Accounts.
 */
interface IERC7579Account {
    event ModuleInstalled(uint256 indexed moduleTypeId, address indexed module);
    event ModuleUninstalled(uint256 indexed moduleTypeId, address indexed module);

    function execute(bytes32 mode, bytes calldata executionCalldata) external payable;
    function executeFromExecutor(bytes32 mode, bytes calldata executionCalldata)
        external
        payable
        returns (bytes[] memory returnData);
    function installModule(uint256 moduleTypeId, address module, bytes calldata initData) external;
    function uninstallModule(uint256 moduleTypeId, address module, bytes calldata deInitData) external;
    function isModuleInstalled(uint256 moduleTypeId, address module, bytes calldata additionalContext)
        external
        view
        returns (bool);
    function accountId() external view returns (string memory);
}

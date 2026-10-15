// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import { IERC7579Account, Execution, MODULE_TYPE_VALIDATOR, MODULE_TYPE_EXECUTOR, MODULE_TYPE_HOOK } from "./interfaces/IERC7579Account.sol";
import { IERC7579Hook } from "./interfaces/IERC7579Hook.sol";
import { IERC7579Validator } from "./interfaces/IERC7579Validator.sol";
import { PackedUserOperation } from "./interfaces/PackedUserOperation.sol";

/**
 * @title TecAccount
 * @author Tec-C Core Engineering Team (FinTechathon 2026 Topic F)
 * @notice Enterprise-grade ERC-7579 Modular Smart Account.
 * @dev Decouples AI cognitive planning from on-chain execution.
 *      Enforces immutable preCheck and postCheck policies via TetherGuardHook.
 */
contract TecAccount is IERC7579Account {
    string public constant ACCOUNT_ID = "tec-c.smart-account.v1";

    address public rootOwner; // Biometric Passkey / WebAuthn FaceID owner
    address public immutable entryPoint;

    // Installed ERC-7579 Modules
    IERC7579Hook public installedHook;
    IERC7579Validator public installedValidator;
    mapping(address => bool) public installedExecutors;

    event TecAccountInitialized(address indexed rootOwner, address indexed entryPoint);
    event ExecutionExecuted(address indexed target, uint256 value, bytes callData);

    error OnlyRootOwner();
    error OnlyEntryPointOrOwner();
    error ExecutionFailed(bytes returnData);
    error InvalidModuleType();
    error AlreadyInitialized();

    modifier onlyRootOwner() {
        if (msg.sender != rootOwner) revert OnlyRootOwner();
        _;
    }

    modifier onlyEntryPointOrOwner() {
        if (msg.sender != entryPoint && msg.sender != rootOwner && !installedExecutors[msg.sender]) {
            revert OnlyEntryPointOrOwner();
        }
        _;
    }

    constructor(address _entryPoint) {
        require(_entryPoint != address(0), "INVALID_ENTRYPOINT");
        entryPoint = _entryPoint;
    }

    /**
     * @notice Initialize the TecAccount with Passkey Root Owner and default modules.
     */
    function initialize(
        address _rootOwner,
        address _hook,
        address _validator
    ) external {
        if (rootOwner != address(0)) revert AlreadyInitialized();
        require(_rootOwner != address(0), "INVALID_OWNER");

        rootOwner = _rootOwner;
        if (_hook != address(0)) {
            installedHook = IERC7579Hook(_hook);
            emit ModuleInstalled(MODULE_TYPE_HOOK, _hook);
        }
        if (_validator != address(0)) {
            installedValidator = IERC7579Validator(_validator);
            emit ModuleInstalled(MODULE_TYPE_VALIDATOR, _validator);
        }

        emit TecAccountInitialized(_rootOwner, entryPoint);
    }

    /**
     * @notice Standard ERC-7579 execution entrypoint with preCheck and postCheck hooks.
     */
    function execute(bytes32 /* mode */, bytes calldata executionCalldata) external payable override onlyEntryPointOrOwner {
        _executeWithHook(executionCalldata);
    }

    /**
     * @notice ERC-7579 executor execution pathway.
     */
    function executeFromExecutor(
        bytes32 /* mode */,
        bytes calldata executionCalldata
    ) external payable override returns (bytes[] memory returnData) {
        require(installedExecutors[msg.sender], "UNAUTHORIZED_EXECUTOR");
        returnData = new bytes[](1);
        returnData[0] = _executeWithHook(executionCalldata);
    }

    /**
     * @notice Install an ERC-7579 module (Validator, Hook, Executor).
     */
    function installModule(uint256 moduleTypeId, address module, bytes calldata /* initData */) external override onlyRootOwner {
        if (moduleTypeId == MODULE_TYPE_HOOK) {
            installedHook = IERC7579Hook(module);
        } else if (moduleTypeId == MODULE_TYPE_VALIDATOR) {
            installedValidator = IERC7579Validator(module);
        } else if (moduleTypeId == MODULE_TYPE_EXECUTOR) {
            installedExecutors[module] = true;
        } else {
            revert InvalidModuleType();
        }
        emit ModuleInstalled(moduleTypeId, module);
    }

    /**
     * @notice Uninstall an ERC-7579 module.
     */
    function uninstallModule(uint256 moduleTypeId, address module, bytes calldata /* deInitData */) external override onlyRootOwner {
        if (moduleTypeId == MODULE_TYPE_HOOK) {
            require(address(installedHook) == module, "MISMATCH");
            installedHook = IERC7579Hook(address(0));
        } else if (moduleTypeId == MODULE_TYPE_VALIDATOR) {
            require(address(installedValidator) == module, "MISMATCH");
            installedValidator = IERC7579Validator(address(0));
        } else if (moduleTypeId == MODULE_TYPE_EXECUTOR) {
            installedExecutors[module] = false;
        } else {
            revert InvalidModuleType();
        }
        emit ModuleUninstalled(moduleTypeId, module);
    }

    /**
     * @notice Check whether a module is installed.
     */
    function isModuleInstalled(
        uint256 moduleTypeId,
        address module,
        bytes calldata /* additionalContext */
    ) external view override returns (bool) {
        if (moduleTypeId == MODULE_TYPE_HOOK) return address(installedHook) == module;
        if (moduleTypeId == MODULE_TYPE_VALIDATOR) return address(installedValidator) == module;
        if (moduleTypeId == MODULE_TYPE_EXECUTOR) return installedExecutors[module];
        return false;
    }

    /**
     * @notice ERC-4337 UserOperation validation callback.
     */
    function validateUserOp(
        PackedUserOperation calldata userOp,
        bytes32 userOpHash,
        uint256 missingAccountFunds
    ) external returns (uint256 validationData) {
        require(msg.sender == entryPoint, "ONLY_ENTRYPOINT");

        if (address(installedValidator) != address(0)) {
            validationData = installedValidator.validateUserOp(userOp, userOpHash);
        } else {
            // Direct ECDSA signature validation against rootOwner
            bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", userOpHash));
            address signer = _recover(ethHash, userOp.signature);
            validationData = (signer == rootOwner) ? 0 : 1;
        }

        // Pay prefund if required by EntryPoint
        if (missingAccountFunds > 0) {
            (bool success, ) = payable(entryPoint).call{value: missingAccountFunds}("");
            (success);
        }
    }

    function accountId() external pure override returns (string memory) {
        return ACCOUNT_ID;
    }

    // --- Internal Execution Engine ---

    function _executeWithHook(bytes calldata executionCalldata) internal returns (bytes memory result) {
        bytes memory hookData;
        (address target, uint256 value, bytes memory data) = _decodeExecution(executionCalldata);

        // 1. Pre-execution Hook verification
        if (address(installedHook) != address(0)) {
            hookData = installedHook.preCheck(msg.sender, value, executionCalldata);
        }

        // 2. Perform On-Chain Execution (emit audit event first to guard log ordering)
        emit ExecutionExecuted(target, value, data);

        bool success;
        (success, result) = target.call{value: value}(data);
        if (!success) {
            revert ExecutionFailed(result);
        }

        // 3. Post-execution Hook verification
        if (address(installedHook) != address(0)) {
            installedHook.postCheck(hookData);
        }
    }

    function _decodeExecution(bytes calldata executionCalldata) internal pure returns (address target, uint256 value, bytes memory data) {
        require(executionCalldata.length >= 52, "INVALID_CALLDATA");
        // Layout: target (20 bytes) || value (32 bytes) || callData (variable)
        target = address(bytes20(executionCalldata[0:20]));
        value = uint256(bytes32(executionCalldata[20:52]));
        data = executionCalldata[52:];
    }

    function _recover(bytes32 hash, bytes memory signature) internal pure returns (address) {
        if (signature.length != 65) return address(0);
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := mload(add(signature, 0x20))
            s := mload(add(signature, 0x40))
            v := byte(0, mload(add(signature, 0x60)))
        }
        // Enforce lower-s to protect against signature malleability (EIP-2)
        if (uint256(s) > 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0) {
            return address(0);
        }
        if (v < 27) v += 27;
        if (v != 27 && v != 28) return address(0);
        return ecrecover(hash, v, r, s);
    }

    receive() external payable {}
}

// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {
    IERC7579Account,
    Execution,
    MODULE_TYPE_VALIDATOR,
    MODULE_TYPE_EXECUTOR,
    MODULE_TYPE_HOOK
} from "./interfaces/IERC7579Account.sol";
import {IERC7579Hook} from "./interfaces/IERC7579Hook.sol";
import {IERC7579Validator} from "./interfaces/IERC7579Validator.sol";
import {PackedUserOperation} from "./interfaces/PackedUserOperation.sol";

/**
 * @title TecAccount
 * @author Tec-C Core Engineering Team (FinTechathon 2026 Topic F)
 * @notice Enterprise-grade ERC-7579 Modular Smart Account.
 * @dev Decouples AI cognitive planning from on-chain execution.
 *      Enforces immutable preCheck and postCheck policies via TetherGuardHook.
 */
contract TecAccount is IERC7579Account {
    /// @notice Unique identifier for this modular account implementation
    string public constant ACCOUNT_ID = "tec-c.smart-account.v1";

    /// @notice Biometric Passkey / WebAuthn FaceID owner authorized for account administration
    address public rootOwner;
    /// @notice Canonical ERC-4337 EntryPoint address
    address public immutable entryPoint;
    /// @notice Deployer address authorized for one-time initialization
    address public immutable deployer;

    /// @notice Installed ERC-7579 execution policy hook enforcing Tether Radius and telemetry
    IERC7579Hook public installedHook;
    /// @notice Installed ERC-7579 signature validation module
    IERC7579Validator public installedValidator;
    /// @notice Mapping tracking authorized execution modules (e.g. AI agent executors)
    mapping(address => bool) public installedExecutors;

    /**
     * @notice Emitted when the account is initialized with its root owner and entry point.
     * @param rootOwner The Passkey / WebAuthn root owner address.
     * @param entryPoint The canonical ERC-4337 EntryPoint address.
     */
    event TecAccountInitialized(address indexed rootOwner, address indexed entryPoint);

    /**
     * @notice Emitted immediately prior to target execution for audit and log-ordering telemetry.
     * @param target The destination contract address.
     * @param value Native ETH transmitted with the call.
     * @param callData The payload executed on the target contract.
     */
    event ExecutionExecuted(address indexed target, uint256 value, bytes callData);

    /// @notice Reverts if caller is not the registered Passkey root owner.
    error OnlyRootOwner();
    /// @notice Reverts if caller is not the EntryPoint, root owner, or an authorized executor.
    error OnlyEntryPointOrOwner();
    /// @notice Reverts if external execution call fails.
    /// @param returnData Low-level revert data returned by the failed execution.
    error ExecutionFailed(bytes returnData);
    /// @notice Reverts if an unsupported module type ID is supplied.
    error InvalidModuleType();
    /// @notice Reverts if account has already been initialized.
    error AlreadyInitialized();

    /// @dev Restricts invocation strictly to the Passkey root owner.
    modifier onlyRootOwner() {
        if (msg.sender != rootOwner) revert OnlyRootOwner();
        _;
    }

    /// @dev Restricts invocation to canonical EntryPoint, root owner, or installed executor modules.
    modifier onlyEntryPointOrOwner() {
        if (msg.sender != entryPoint && msg.sender != rootOwner && !installedExecutors[msg.sender]) {
            revert OnlyEntryPointOrOwner();
        }
        _;
    }

    /**
     * @notice Constructor setting the immutable EntryPoint address and deployer.
     * @param _entryPoint Canonical ERC-4337 EntryPoint contract address.
     */
    constructor(address _entryPoint) {
        require(_entryPoint != address(0), "INVALID_ENTRYPOINT");
        entryPoint = _entryPoint;
        deployer = msg.sender;
    }

    /**
     * @notice Initializes the TecAccount with Passkey Root Owner and default modules.
     * @dev Callable only once by the deployer during factory deployment.
     * @param _rootOwner Address of the Passkey / WebAuthn root owner.
     * @param _hook Optional initial execution hook address (TetherGuardHook).
     * @param _validator Optional initial validator module address (SessionKeyValidator).
     */
    function initialize(address _rootOwner, address _hook, address _validator) external {
        if (rootOwner != address(0)) revert AlreadyInitialized();
        require(_rootOwner != address(0), "INVALID_OWNER");
        require(msg.sender == deployer, "UNAUTHORIZED_INIT");

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
     * @dev Unpacks target, value, data and triggers preCheck/postCheck policy enforcement.
     * @param mode Execution mode (e.g. single execution mode 0x00).
     * @param executionCalldata Packed execution payload: target (20B) || value (32B) || callData.
     */
    function execute(bytes32 mode, bytes calldata executionCalldata) external payable override onlyEntryPointOrOwner {
        mode; // silence unused parameter warning
        _executeWithHook(executionCalldata);
    }

    /**
     * @notice ERC-7579 executor execution pathway for authorized AI session modules.
     * @dev Restricted to modules registered in `installedExecutors`.
     * @param mode Execution mode.
     * @param executionCalldata Packed execution payload: target (20B) || value (32B) || callData.
     * @return returnData Array containing low-level execution return bytes.
     */
    function executeFromExecutor(bytes32 mode, bytes calldata executionCalldata)
        external
        payable
        override
        returns (bytes[] memory returnData)
    {
        mode; // silence unused parameter warning
        require(installedExecutors[msg.sender], "UNAUTHORIZED_EXECUTOR");
        returnData = new bytes[](1);
        returnData[0] = _executeWithHook(executionCalldata);
    }

    /**
     * @notice Installs an ERC-7579 module (Validator, Hook, Executor).
     * @dev Restricted to the root owner.
     * @param moduleTypeId Numeric identifier of module type (1: Validator, 2: Executor, 4: Hook).
     * @param module Address of module contract to install.
     * @param initData Optional initialization data passed to module.
     */
    function installModule(uint256 moduleTypeId, address module, bytes calldata initData)
        external
        override
        onlyRootOwner
    {
        initData; // silence unused parameter warning
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
     * @notice Uninstalls an ERC-7579 module.
     * @dev Restricted to the root owner.
     * @param moduleTypeId Numeric identifier of module type.
     * @param module Address of module contract to uninstall.
     * @param deInitData Optional de-initialization data passed to module.
     */
    function uninstallModule(uint256 moduleTypeId, address module, bytes calldata deInitData)
        external
        override
        onlyRootOwner
    {
        deInitData; // silence unused parameter warning
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
     * @notice Checks whether a specific module is currently installed.
     * @param moduleTypeId Numeric identifier of module type.
     * @param module Address of module to query.
     * @param additionalContext Contextual data.
     * @return True if module is currently installed.
     */
    function isModuleInstalled(uint256 moduleTypeId, address module, bytes calldata additionalContext)
        external
        view
        override
        returns (bool)
    {
        additionalContext; // silence unused parameter warning
        if (moduleTypeId == MODULE_TYPE_HOOK) return address(installedHook) == module;
        if (moduleTypeId == MODULE_TYPE_VALIDATOR) return address(installedValidator) == module;
        if (moduleTypeId == MODULE_TYPE_EXECUTOR) return installedExecutors[module];
        return false;
    }

    /**
     * @notice ERC-4337 UserOperation validation callback.
     * @dev Forwards to installed validator or validates direct rootOwner ECDSA signature.
     * @param userOp The packed user operation structure.
     * @param userOpHash Hash of user operation calculated by EntryPoint.
     * @param missingAccountFunds Gas prefund shortfall required by EntryPoint.
     * @return validationData Packed validation data (0 for success, 1 for signature failure).
     */
    function validateUserOp(PackedUserOperation calldata userOp, bytes32 userOpHash, uint256 missingAccountFunds)
        external
        returns (uint256 validationData)
    {
        require(msg.sender == entryPoint, "ONLY_ENTRYPOINT");

        if (address(installedValidator) != address(0)) {
            validationData = installedValidator.validateUserOp(userOp, userOpHash);
        } else {
            // Direct ECDSA signature validation against rootOwner (SEC-06: Reject if rootOwner is address(0))
            if (rootOwner == address(0)) return 1;
            bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", userOpHash));
            address signer = _recover(ethHash, userOp.signature);
            validationData = (signer != address(0) && signer == rootOwner) ? 0 : 1;
        }

        // Pay prefund if required by EntryPoint
        if (missingAccountFunds > 0) {
            (bool success,) = payable(entryPoint).call{value: missingAccountFunds}("");
            (success);
        }
    }

    /**
     * @notice Returns the account implementation identifier.
     * @return Unique string identifier for TecAccount.
     */
    function accountId() external pure override returns (string memory) {
        return ACCOUNT_ID;
    }

    // --- Internal Execution Engine ---

    /**
     * @dev Executes a transaction with preCheck and postCheck hook verification.
     * @param executionCalldata Packed execution payload: target (20B) || value (32B) || callData.
     * @return result Low-level return data from the target execution.
     */
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

    /**
     * @dev Decodes packed execution calldata into target, value, and callData components.
     * @param executionCalldata Packed payload with layout target (20B) || value (32B) || callData.
     * @return target Destination contract address.
     * @return value Native ETH transmitted with call.
     * @return data Calldata executed on destination contract.
     */
    function _decodeExecution(bytes calldata executionCalldata)
        internal
        pure
        returns (address target, uint256 value, bytes memory data)
    {
        require(executionCalldata.length >= 52, "INVALID_CALLDATA");
        // Layout: target (20 bytes) || value (32 bytes) || callData (variable)
        target = address(bytes20(executionCalldata[0:20]));
        value = uint256(bytes32(executionCalldata[20:52]));
        data = executionCalldata[52:];
    }

    /**
     * @dev Cryptographically recovers signer address from hash and 65-byte ECDSA signature.
     * @param hash 32-byte digest that was signed.
     * @param signature 65-byte ECDSA signature (r, s, v).
     * @return Recovered signer address (or address(0) if signature is invalid/malleable).
     */
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

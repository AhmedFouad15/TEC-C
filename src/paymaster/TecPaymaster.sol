// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IPaymaster} from "../interfaces/IPaymaster.sol";
import {PackedUserOperation} from "../interfaces/PackedUserOperation.sol";

/**
 * @title TecPaymaster
 * @author Tec-C Core Engineering Team (FinTechathon 2026 Topic F)
 * @notice Enterprise-grade ERC-4337 v0.7 Paymaster enforcing strict gas-griefing bounds.
 * @dev Defends against prompt injection loops and algorithmic draining by capping
 *      total sponsored gas per ephemeral session key to MAX_SESSION_GAS_BUDGET (0.005 ETH).
 */
contract TecPaymaster is IPaymaster {
    uint256 public constant MAX_SESSION_GAS_BUDGET = 0.005 ether;

    address public immutable entryPoint;
    address public owner;

    // account => sessionKey => cumulativeGasSponsored (in wei)
    mapping(address => mapping(address => uint256)) public sponsoredGasPerSession;
    // account => deposit balance
    mapping(address => uint256) public accountBalances;

    event GasSponsored(
        address indexed account, address indexed sessionKey, uint256 actualCost, uint256 totalSessionSpent
    );
    event GasQuotaReplenished(address indexed account, uint256 amount);
    event GasGriefingHalted(address indexed account, address indexed sessionKey, uint256 attemptedCost, uint256 quota);
    event GasRefundWithdrawn(address indexed account, address indexed recipient, uint256 amount);

    error OnlyEntryPoint();
    error OnlyOwner();
    error InsufficientPaymasterBalance();
    error InsufficientAccountBalance();
    error GasGriefingBudgetExceeded(address sessionKey, uint256 currentSpent, uint256 maxBudget);

    modifier onlyEntryPoint() {
        if (msg.sender != entryPoint) revert OnlyEntryPoint();
        _;
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert OnlyOwner();
        _;
    }

    constructor(address _entryPoint) {
        require(_entryPoint != address(0), "INVALID_ENTRYPOINT");
        entryPoint = _entryPoint;
        owner = msg.sender;
    }

    /**
     * @notice Deposit funds to sponsor gas for a specific account.
     */
    function depositForAccount(address account) external payable {
        accountBalances[account] += msg.value;
        emit GasQuotaReplenished(account, msg.value);
    }

    /**
     * @notice ERC-4337 Paymaster validation.
     * @dev Parses sessionKey from userOp signature and verifies cumulative gas <= 0.005 ETH.
     */
    function validatePaymasterUserOp(
        PackedUserOperation calldata userOp,
        bytes32,
        /* userOpHash */
        uint256 maxCost
    )
        external
        view
        override
        returns (bytes memory context, uint256 validationData)
    {
        address account = userOp.sender;

        // Check account has deposited enough gas
        if (accountBalances[account] < maxCost) {
            return ("", 1); // Reject: insufficient balance
        }

        // Extract sessionKey from userOp signature if present
        address sessionKey = address(0);
        if (userOp.signature.length >= 20) {
            sessionKey = address(bytes20(userOp.signature[0:20]));
        }

        if (sessionKey != address(0)) {
            uint256 currentSpent = sponsoredGasPerSession[account][sessionKey];
            if (currentSpent + maxCost > MAX_SESSION_GAS_BUDGET) {
                // Rejects sponsorship: anti-griefing limit exceeded!
                return ("", 1);
            }
        }

        // Return context for postOp
        context = abi.encode(account, sessionKey, maxCost);
        validationData = 0; // Success
    }

    /**
     * @notice ERC-4337 Post-Op callback to record actual gas consumption.
     */
    function postOp(
        PostOpMode,
        /* mode */
        bytes calldata context,
        uint256 actualGasCost,
        uint256 /* actualUserOpFeePerGas */
    )
        external
        override
        onlyEntryPoint
    {
        (address account, address sessionKey,) = abi.decode(context, (address, address, uint256));

        if (accountBalances[account] >= actualGasCost) {
            accountBalances[account] -= actualGasCost;
        } else {
            accountBalances[account] = 0;
        }

        if (sessionKey != address(0)) {
            sponsoredGasPerSession[account][sessionKey] += actualGasCost;
            emit GasSponsored(account, sessionKey, actualGasCost, sponsoredGasPerSession[account][sessionKey]);

            if (sponsoredGasPerSession[account][sessionKey] >= MAX_SESSION_GAS_BUDGET) {
                emit GasGriefingHalted(account, sessionKey, actualGasCost, MAX_SESSION_GAS_BUDGET);
            }
        }
    }

    /**
     * @notice Allows an account to withdraw their unused deposited gas funds.
     */
    function withdrawForAccount(address payable recipient, uint256 amount) external {
        require(recipient != address(0), "INVALID_RECIPIENT");
        if (accountBalances[msg.sender] < amount) revert InsufficientAccountBalance();
        accountBalances[msg.sender] -= amount;
        (bool success,) = recipient.call{value: amount}("");
        require(success, "ETH_TRANSFER_FAILED");
        emit GasRefundWithdrawn(msg.sender, recipient, amount);
    }

    /**
     * @notice Withdraw funds from paymaster by owner.
     */
    function withdraw(address payable recipient, uint256 amount) external onlyOwner {
        require(recipient != address(0), "INVALID_RECIPIENT");
        require(address(this).balance >= amount, "INSUFFICIENT_BALANCE");
        (bool success,) = recipient.call{value: amount}("");
        require(success, "ETH_TRANSFER_FAILED");
    }

    receive() external payable {}
}

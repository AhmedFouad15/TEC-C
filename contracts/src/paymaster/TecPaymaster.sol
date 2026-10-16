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
    /// @notice Maximum cumulative gas budget sponsored per ephemeral session key (0.005 ETH)
    uint256 public constant MAX_SESSION_GAS_BUDGET = 0.005 ether;

    /// @notice Canonical ERC-4337 EntryPoint contract address
    address public immutable entryPoint;
    /// @notice Paymaster contract owner authorized for surplus treasury management
    address public owner;

    /// @notice Cumulative gas sponsored per account per session key: account => sessionKey => cumulativeGas (in wei)
    mapping(address => mapping(address => uint256)) public sponsoredGasPerSession;
    /// @notice Prepaid corporate gas deposit balance per account: account => depositBalance (in wei)
    mapping(address => uint256) public accountBalances;
    /// @notice Aggregate user deposits tracked to prevent owner rug-pull of client funds (SEC-02)
    uint256 public totalUserDeposits;

    /**
     * @notice Emitted when gas is sponsored for an account's session key.
     * @param account The smart account sponsored.
     * @param sessionKey The ephemeral session key executing the transaction.
     * @param actualCost Gas cost incurred by this specific transaction.
     * @param totalSessionSpent Cumulative gas sponsored for this session key.
     */
    event GasSponsored(
        address indexed account, address indexed sessionKey, uint256 actualCost, uint256 totalSessionSpent
    );

    /**
     * @notice Emitted when an account deposits additional ETH into their gas sponsorship quota.
     * @param account The smart account replenishing its deposit.
     * @param amount The ETH amount deposited.
     */
    event GasQuotaReplenished(address indexed account, uint256 amount);

    /**
     * @notice Emitted when an AI session key hits the 0.005 ETH anti-griefing ceiling.
     * @param account The smart account affected.
     * @param sessionKey The ephemeral session key that was halted.
     * @param attemptedCost Gas cost attempted that breached the quota.
     * @param quota The maximum gas budget threshold (0.005 ETH).
     */
    event GasGriefingHalted(address indexed account, address indexed sessionKey, uint256 attemptedCost, uint256 quota);

    /**
     * @notice Emitted when an account withdraws its unused prepaid gas deposit.
     * @param account The smart account requesting the refund.
     * @param recipient Destination address receiving the refund.
     * @param amount The ETH amount refunded.
     */
    event GasRefundWithdrawn(address indexed account, address indexed recipient, uint256 amount);

    /// @notice Reverts if caller is not the canonical EntryPoint.
    error OnlyEntryPoint();
    /// @notice Reverts if caller is not the paymaster owner.
    error OnlyOwner();
    /// @notice Reverts if global paymaster ETH balance is insufficient.
    error InsufficientPaymasterBalance();
    /// @notice Reverts if account's individual prepaid deposit balance is insufficient.
    error InsufficientAccountBalance();
    /// @notice Reverts if session key exceeds the 0.005 ETH cumulative gas budget.
    /// @param sessionKey The ephemeral session key address.
    /// @param currentSpent Cumulative gas already consumed.
    /// @param maxBudget The maximum permitted session gas budget.
    error GasGriefingBudgetExceeded(address sessionKey, uint256 currentSpent, uint256 maxBudget);
    /// @notice Reverts if owner attempts to withdraw funds belonging to user deposits.
    /// @param requested The withdrawal amount requested.
    /// @param surplus The available owner surplus balance.
    error CannotWithdrawUserDeposits(uint256 requested, uint256 surplus);

    /// @dev Restricts invocation strictly to the EntryPoint contract.
    modifier onlyEntryPoint() {
        if (msg.sender != entryPoint) revert OnlyEntryPoint();
        _;
    }

    /// @dev Restricts invocation strictly to the paymaster owner.
    modifier onlyOwner() {
        if (msg.sender != owner) revert OnlyOwner();
        _;
    }

    /**
     * @notice Constructor setting canonical EntryPoint address and initial owner.
     * @param _entryPoint Canonical ERC-4337 EntryPoint contract address.
     */
    constructor(address _entryPoint) {
        require(_entryPoint != address(0), "INVALID_ENTRYPOINT");
        entryPoint = _entryPoint;
        owner = msg.sender;
    }

    /**
     * @notice Deposits ETH to sponsor gas for a specific corporate smart account.
     * @param account The smart account address receiving the gas credit.
     */
    function depositForAccount(address account) external payable {
        accountBalances[account] += msg.value;
        totalUserDeposits += msg.value;
        emit GasQuotaReplenished(account, msg.value);
    }

    /**
     * @notice ERC-4337 Paymaster validation verifying account balance and session budget.
     * @dev Extracts session key from signature and enforces 0.005 ETH anti-griefing cap.
     * @param userOp The packed ERC-4337 UserOperation.
     * @param maxCost Maximum gas cost that the operation could incur.
     * @return context Context byte payload passed to postOp.
     * @return validationData Packed validation status (0 for approval, 1 for rejection).
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

        // Extract sessionKey from userOp signature if present.
        // Direct rootOwner ECDSA signatures are exactly 65 bytes (r, s, v), not session keys.
        // Ephemeral session keys prepend a 20-byte sessionKey address (e.g. 85 bytes: sessionKey + ECDSA sig).
        address sessionKey = address(0);
        if (userOp.signature.length >= 20 && userOp.signature.length != 65) {
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
     * @notice ERC-4337 Post-Op callback to record actual gas consumption and debit escrow.
     * @param context Context returned by validatePaymasterUserOp.
     * @param actualGasCost Actual gas fee incurred by the execution.
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

        uint256 deducted = accountBalances[account] >= actualGasCost ? actualGasCost : accountBalances[account];
        accountBalances[account] -= deducted;
        totalUserDeposits = totalUserDeposits >= deducted ? totalUserDeposits - deducted : 0;

        if (sessionKey != address(0)) {
            sponsoredGasPerSession[account][sessionKey] += actualGasCost;
            emit GasSponsored(account, sessionKey, actualGasCost, sponsoredGasPerSession[account][sessionKey]);

            if (sponsoredGasPerSession[account][sessionKey] >= MAX_SESSION_GAS_BUDGET) {
                emit GasGriefingHalted(account, sessionKey, actualGasCost, MAX_SESSION_GAS_BUDGET);
            }
        }
    }

    /**
     * @notice Allows an account to safely self-withdraw their unused deposited gas funds.
     * @param recipient Destination address to receive the refunded ETH.
     * @param amount ETH amount to withdraw.
     */
    function withdrawForAccount(address payable recipient, uint256 amount) external {
        require(recipient != address(0), "INVALID_RECIPIENT");
        if (accountBalances[msg.sender] < amount) revert InsufficientAccountBalance();
        accountBalances[msg.sender] -= amount;
        totalUserDeposits = totalUserDeposits >= amount ? totalUserDeposits - amount : 0;
        (bool success,) = recipient.call{value: amount}("");
        require(success, "ETH_TRANSFER_FAILED");
        emit GasRefundWithdrawn(msg.sender, recipient, amount);
    }

    /**
     * @notice Withdraws excess treasury surplus funds from paymaster without touching user deposits (SEC-02).
     * @dev Strictly bounds withdrawal to `address(this).balance - totalUserDeposits`.
     * @param recipient Destination address to receive the surplus ETH.
     * @param amount ETH amount to withdraw.
     */
    function withdraw(address payable recipient, uint256 amount) external onlyOwner {
        require(recipient != address(0), "INVALID_RECIPIENT");
        uint256 surplus = address(this).balance > totalUserDeposits ? address(this).balance - totalUserDeposits : 0;
        if (amount > surplus) revert CannotWithdrawUserDeposits(amount, surplus);
        (bool success,) = recipient.call{value: amount}("");
        require(success, "ETH_TRANSFER_FAILED");
    }

    /**
     * @notice Deposits ETH from paymaster balance into the EntryPoint contract (SEC-03).
     * @dev Restricted strictly to the paymaster contract owner.
     */
    function depositToEntryPoint() external payable onlyOwner {
        (bool success,) =
            entryPoint.call{value: msg.value}(abi.encodeWithSignature("depositTo(address)", address(this)));
        if (!success) {
            (bool s2,) = payable(entryPoint).call{value: msg.value}("");
            require(s2, "ENTRYPOINT_DEPOSIT_FAILED");
        }
    }

    /**
     * @notice Withdraws ETH from EntryPoint balance back to a specified recipient (SEC-03).
     * @dev Restricted strictly to the paymaster contract owner.
     * @param recipient Destination address to receive the withdrawn funds.
     * @param amount ETH amount to withdraw.
     */
    function withdrawFromEntryPoint(address payable recipient, uint256 amount) external onlyOwner {
        require(recipient != address(0), "INVALID_RECIPIENT");
        (bool success,) = entryPoint.call(abi.encodeWithSignature("withdrawTo(address,uint256)", recipient, amount));
        require(success, "ENTRYPOINT_WITHDRAW_FAILED");
    }

    receive() external payable {}
}

// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import { IERC7579Hook } from "../interfaces/IERC7579Hook.sol";

/**
 * @title TetherGuardHook
 * @author Tec-C Core Engineering Team (FinTechathon 2026 Topic F)
 * @notice Immutable security hook enforcing "The Tether Radius" (spending velocity limit),
 *         target protocol whitelisting, and dual-axis risk tier policy.
 * @dev Replaces legacy policy guards with an institutional-grade EVM bytecode tether.
 *      Enforces strict separation between AI Session Keys and the Passkey Root Owner.
 *      Any action exceeding The Tether Radius reverts unless escalated ("Breaking the Tether").
 */
contract TetherGuardHook is IERC7579Hook {
    // --- Risk Tiers (Dual-Axis Risk Engine) ---
    uint8 public constant RISK_TIER_CONSERVATIVE = 1; // Tier 1: Staking, Blue-Chips, Shibor/MMFs, Tokenized Gold
    uint8 public constant RISK_TIER_BALANCED     = 2; // Tier 2: Liquid Staking Tokens (stETH), Major AMMs
    uint8 public constant RISK_TIER_AGGRESSIVE   = 3; // Tier 3: Concentrated Liquidity, Long-Tail LPs

    // --- State Storage Per Account ---
    struct AccountPolicy {
        uint256 tetherRadius;       // Max daily spending radius (e.g. 500 ether or USD-equivalent wei)
        uint256 dailySpent;         // Aggregate spent in current 24h epoch
        uint256 currentEpoch;       // Current epoch index: block.timestamp / 1 days
        uint8 riskTier;             // User's active risk tolerance tier (1, 2, or 3)
        bool emergencyPaused;       // Circuit breaker triggered by PegGuard NLP Sentinel
        address rootOwner;          // Passkey WebAuthn FaceID root owner
    }

    mapping(address => AccountPolicy) public policies;
    mapping(address => mapping(address => bool)) public whitelistedTargets;
    mapping(address => mapping(address => uint8)) public targetRiskTiers;
    mapping(address => mapping(address => bool)) public authorizedSessionKeys;

    uint256 public totalAuditedExecutions;

    // --- Events for WeBank WeIdentity Audit Trails ---
    event TetherRadiusConfigured(address indexed account, uint256 newRadius, uint8 riskTier);
    event TetherRadiusConsumed(address indexed account, uint256 amount, uint256 remainingRadius, uint256 epoch);
    event TetherBroken(address indexed account, address indexed rootOwner, uint256 amount, address indexed target);
    event TargetWhitelisted(address indexed account, address indexed target, uint8 riskTier, bool status);
    event SessionKeyAuthorized(address indexed account, address indexed sessionKey, bool status);
    event EmergencyCircuitBreakerTriggered(address indexed account, string reason);
    event EmergencyCircuitBreakerReset(address indexed account);
    event PostExecutionAudited(address indexed account, bool isRoot, uint256 value, address indexed target, uint256 auditIndex);

    // --- Custom Errors ---
    error TetherRadiusExceeded(uint256 attempted, uint256 remainingRadius);
    error UnauthorizedTarget(address target);
    error AssetTierNotPermitted(address target, uint8 targetTier, uint8 allowedTier);
    error EmergencyCircuitBreakerActive();
    error UnauthorizedCaller();
    error InvalidTetherRadius();

    modifier onlyAccountOrOwner(address account) {
        if (msg.sender != account && msg.sender != policies[account].rootOwner) {
            revert UnauthorizedCaller();
        }
        _;
    }

    /**
     * @notice Initializes policy parameters for a new Tec-C Smart Account.
     * @param account The address of the smart account.
     * @param rootOwner The Passkey / WebAuthn root owner address.
     * @param initialRadius The initial daily spending tether radius.
     * @param initialRiskTier The user's risk tolerance tier (1, 2, or 3).
     */
    function initializeAccountPolicy(
        address account,
        address rootOwner,
        uint256 initialRadius,
        uint8 initialRiskTier
    ) external {
        AccountPolicy storage p = policies[account];
        require(p.rootOwner == address(0), "ALREADY_INITIALIZED");
        require(initialRadius > 0, "INVALID_RADIUS");
        require(initialRiskTier >= RISK_TIER_CONSERVATIVE && initialRiskTier <= RISK_TIER_AGGRESSIVE, "INVALID_TIER");

        p.rootOwner = rootOwner;
        p.tetherRadius = initialRadius;
        p.riskTier = initialRiskTier;
        p.currentEpoch = block.timestamp / 1 days;

        emit TetherRadiusConfigured(account, initialRadius, initialRiskTier);
    }

    /**
     * @notice Updates The Tether Radius or Risk Tier (can only be called by root owner or account).
     */
    function setTetherRadius(
        address account,
        uint256 newRadius,
        uint8 newRiskTier
    ) external onlyAccountOrOwner(account) {
        if (newRadius == 0) revert InvalidTetherRadius();
        require(newRiskTier >= RISK_TIER_CONSERVATIVE && newRiskTier <= RISK_TIER_AGGRESSIVE, "INVALID_TIER");

        AccountPolicy storage p = policies[account];
        p.tetherRadius = newRadius;
        p.riskTier = newRiskTier;

        emit TetherRadiusConfigured(account, newRadius, newRiskTier);
    }

    /**
     * @notice Whitelists an on-chain protocol and sets its risk tier rating.
     */
    function setTargetWhitelist(
        address account,
        address target,
        bool status,
        uint8 tier
    ) external onlyAccountOrOwner(account) {
        whitelistedTargets[account][target] = status;
        targetRiskTiers[account][target] = tier;

        emit TargetWhitelisted(account, target, tier, status);
    }

    /**
     * @notice Authorizes or revokes an ephemeral AI Agent session key.
     */
    function setSessionKeyAuthorization(
        address account,
        address sessionKey,
        bool status
    ) external onlyAccountOrOwner(account) {
        authorizedSessionKeys[account][sessionKey] = status;
        emit SessionKeyAuthorized(account, sessionKey, status);
    }

    /**
     * @notice PegGuard Layer 4 Financial NLP Sentinel Emergency Circuit Breaker.
     * @dev Halts all autonomous session key actions during adverse news events.
     */
    function triggerEmergencyCircuitBreaker(address account, string calldata reason) external onlyAccountOrOwner(account) {
        policies[account].emergencyPaused = true;
        emit EmergencyCircuitBreakerTriggered(account, reason);
    }

    /**
     * @notice Resets emergency circuit breaker after sentiment stabilizes.
     */
    function resetEmergencyCircuitBreaker(address account) external onlyAccountOrOwner(account) {
        policies[account].emergencyPaused = false;
        emit EmergencyCircuitBreakerReset(account);
    }

    /**
     * @notice ERC-7579 Pre-execution Hook verification.
     * @dev Enforces The Tether Radius and target whitelist before the smart account executes.
     */
    function preCheck(
        address msgSender,
        uint256 value,
        bytes calldata msgData
    ) external override returns (bytes memory hookData) {
        address account = msg.sender;
        AccountPolicy storage p = policies[account];

        address target = _extractTarget(msgData);

        // 1. If Root Owner is calling directly: "Breaking the Tether" is authorized!
        if (msgSender == p.rootOwner) {
            emit TetherBroken(account, p.rootOwner, value, target);
            return abi.encode(true, account, value, target);
        }

        // 2. Otherwise caller is an AI Agent session key: enforce strict tether
        if (p.emergencyPaused) {
            revert EmergencyCircuitBreakerActive();
        }

        // 3. Roll epoch if 24 hours elapsed
        uint256 currentEpoch = block.timestamp / 1 days;
        if (p.currentEpoch != currentEpoch) {
            p.currentEpoch = currentEpoch;
            p.dailySpent = 0;
        }

        // 4. Verify target protocol whitelist & risk tier
        if (!whitelistedTargets[account][target]) {
            revert UnauthorizedTarget(target);
        }

        uint8 targetTier = targetRiskTiers[account][target];
        if (targetTier > p.riskTier) {
            revert AssetTierNotPermitted(target, targetTier, p.riskTier);
        }

        // 5. Enforce The Tether Radius (Daily Velocity Limit)
        uint256 remainingRadius = p.tetherRadius > p.dailySpent ? p.tetherRadius - p.dailySpent : 0;
        if (value > remainingRadius) {
            revert TetherRadiusExceeded(value, remainingRadius);
        }

        p.dailySpent += value;
        emit TetherRadiusConsumed(account, value, remainingRadius - value, currentEpoch);

        return abi.encode(false, account, value, target);
    }

    /**
     * @notice ERC-7579 Post-execution Hook callback for WeIdentity audit logs.
     */
    function postCheck(bytes calldata hookData) external override {
        // Unpack hookData for telemetry confirmation
        (bool isRoot, address account, uint256 value, address target) = abi.decode(
            hookData,
            (bool, address, uint256, address)
        );
        require(account == msg.sender, "INVALID_POST_ACCOUNT");

        totalAuditedExecutions++;
        emit PostExecutionAudited(account, isRoot, value, target, totalAuditedExecutions);
    }

    /**
     * @notice View remaining spending radius in current 24h epoch.
     */
    function getRemainingRadius(address account) external view returns (uint256) {
        AccountPolicy storage p = policies[account];
        uint256 currentEpoch = block.timestamp / 1 days;
        if (p.currentEpoch != currentEpoch) {
            return p.tetherRadius;
        }
        return p.tetherRadius > p.dailySpent ? p.tetherRadius - p.dailySpent : 0;
    }

    /**
     * @dev Helper to extract the destination target from execution calldata.
     */
    function _extractTarget(bytes calldata msgData) internal pure returns (address target) {
        if (msgData.length >= 20) {
            // First 20 bytes of execution data encode target address in standard ERC-7579 single exec
            target = address(bytes20(msgData[0:20]));
        } else {
            target = address(0);
        }
    }
}

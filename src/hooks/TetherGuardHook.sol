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
    // --- Risk Tiers (Dual-Axis Risk Engine - Axis 1: Asset Universe) ---
    // Tier 1: Core Preservation & Mega Assets (Giga Tokens: BTC/ETH, Stablecoins: USDC/USDT/e-CNY, Commodities: PAXG Gold/Silver, Shibor MMFs)
    uint8 public constant RISK_TIER_CORE_PRESERVATION = 1;
    // Tier 2: Growth & Active DeFi (Merged Liquid Staking stETH/rETH, AMMs, Curve/Uniswap LPs, Yield Vaults)
    uint8 public constant RISK_TIER_GROWTH_DEFI       = 2;
    // Tier 3: Omni-Universe / Unrestricted (Allows EVERYTHING to be held and traded; zero whitelist restriction, strictly bound by Tether Radius)
    uint8 public constant RISK_TIER_UNRESTRICTED      = 3;

    // Aliases for backwards compatibility
    uint8 public constant RISK_TIER_CONSERVATIVE = 1;
    uint8 public constant RISK_TIER_BALANCED     = 2;
    uint8 public constant RISK_TIER_AGGRESSIVE   = 3;

    // --- Dynamic Elasticity Parameters (Axis 2 Learning Engine - Vault-Native) ---
    uint256 public constant MAX_DAILY_GROWTH_PERCENTAGE = 10;     // Strictly max 10% autonomous increase per day
    uint256 public constant CALIBRATION_COOLDOWN        = 1 days; // Minimum 24 hours between autonomous calibrations
    uint256 public constant STEP_UP_COOLDOWN            = 1 days; // Alias for cooldown

    // --- State Storage Per Account ---
    struct AccountPolicy {
        uint256 tetherRadius;               // Current active daily spending radius
        uint256 baselineRadius;             // Initial baseline radius chosen at onboarding
        uint256 maxElasticCeiling;         // Absolute hard ceiling the AI can NEVER exceed
        uint256 dailySpent;                 // Aggregate spent in current 24h epoch
        uint256 currentEpoch;               // Current epoch index: block.timestamp / 1 days
        uint8 riskTier;                     // User's active risk tolerance tier (1, 2, or 3)
        bool emergencyPaused;               // Circuit breaker triggered by PegGuard NLP Sentinel
        bool isDynamicElasticityEnabled;     // User opt-in: Learn from approved decisions (true) vs strictly limited (false)
        uint256 lastRadiusStepUpTime;      // Timestamp of last autonomous step-up
        uint256 consecutiveRatifications;   // On-chain count of user-ratified transactions without a revert
        address rootOwner;                  // Passkey WebAuthn FaceID root owner
    }

    mapping(address => AccountPolicy) public policies;
    mapping(address => mapping(address => bool)) public whitelistedTargets;
    mapping(address => mapping(address => uint8)) public targetRiskTiers;
    mapping(address => mapping(address => bool)) public authorizedSessionKeys;
    // --- Asynchronous Morning Review System ---
    enum ReviewStatus {
        PENDING_REVIEW,
        LIKED_AND_RATIFIED,
        REVERT_REQUESTED,
        NOTED
    }

    struct AutonomousExecutionRecord {
        uint256 id;
        address target;
        uint256 value;
        uint256 timestamp;
        ReviewStatus status;
        string userNote;
    }

    mapping(address => uint256) public executionCount;
    mapping(address => mapping(uint256 => AutonomousExecutionRecord)) public executionRecords;

    uint256 public totalAuditedExecutions;

    // --- 5-Minute Biometric Verification Window & Sign Approval (Breaking the Tether) ---
    uint256 public constant BIOMETRIC_VERIFICATION_WINDOW = 5 minutes;

    /// @notice Timestamp until which the account has an active biometric verification window (FaceID/TouchID/Passkey)
    mapping(address => uint256) public biometricVerifiedUntil;

    /// @notice Sign approvals (Accept / Reject) given by the user for executions proposed during active biometric window
    mapping(address => mapping(bytes32 => bool)) public signApprovals;

    /// @notice Explicit rejections to prevent rogue execution
    mapping(address => mapping(bytes32 => bool)) public signRejections;

    // --- Events for WeBank WeIdentity Audit Trails ---
    event TetherRadiusConfigured(address indexed account, uint256 newRadius, uint8 riskTier);
    event TetherRadiusConsumed(address indexed account, uint256 amount, uint256 remainingRadius, uint256 epoch);
    event TetherBroken(address indexed account, address indexed caller, uint256 amount, address indexed target);
    event TargetWhitelisted(address indexed account, address indexed target, uint8 riskTier, bool status);
    event SessionKeyAuthorized(address indexed account, address indexed sessionKey, bool status);
    event EmergencyCircuitBreakerTriggered(address indexed account, string reason);
    event EmergencyCircuitBreakerReset(address indexed account);
    event PostExecutionAudited(address indexed account, bool isRoot, uint256 value, address indexed target, uint256 auditIndex);
    event AutonomousRadiusAdjusted(address indexed account, uint256 previousRadius, uint256 newRadius, string rationale);
    event DynamicElasticityToggled(address indexed account, bool enabled, uint256 maxCeiling);
    event AutonomousExecutionLogged(address indexed account, uint256 indexed recordId, address indexed target, uint256 value, uint256 timestamp);
    event TransactionRatified(address indexed account, uint256 indexed recordId, uint256 value, uint256 newDailySpent);
    event TransactionFlaggedForRevert(address indexed account, uint256 indexed recordId, string reason, uint256 penalizedRadius);
    event TransactionNoteSubmitted(address indexed account, uint256 indexed recordId, string note, bool penalizeBrain, uint256 resultingRadius);
    event BiometricVerificationCompleted(address indexed account, address indexed verifier, uint256 validUntil);
    event BiometricVerificationRevoked(address indexed account);
    event SignApprovalSubmitted(address indexed account, bytes32 indexed executionHash, bool approved);

    // --- Custom Errors ---
    error TetherRadiusExceeded(uint256 attempted, uint256 remainingRadius);
    error UnauthorizedTarget(address target);
    error AssetTierNotPermitted(address target, uint8 targetTier, uint8 allowedTier);
    error EmergencyCircuitBreakerActive();
    error UnauthorizedCaller();
    error InvalidTetherRadius();
    error DynamicAdjustmentDisabled();
    error ExceedsElasticCeiling(uint256 proposed, uint256 maxCeiling);
    error StepUpCooldownActive(uint256 nextEligibleTime);
    error ExcessiveStepUpJump(uint256 proposed, uint256 maxAllowed);
    error InvalidRecordId();
    error RecordAlreadyReviewed(ReviewStatus currentStatus);
    error BiometricVerificationRequired();
    error SignApprovalRequired();
    error ExecutionRejectedByUser();
    error InvalidApprovalSignature();

    modifier onlyAccountOrOwner(address account) {
        if (msg.sender != account && msg.sender != policies[account].rootOwner) {
            revert UnauthorizedCaller();
        }
        _;
    }

    /**
     * @notice Initializes policy parameters for a new Tec-C Smart Account with Axis 2 elasticity options.
     * @param account The address of the smart account.
     * @param rootOwner The Passkey / WebAuthn root owner address.
     * @param initialRadius The initial daily spending tether radius (e.g. 10%, 25%, 50%, 100% of liquid budget).
     * @param initialRiskTier The user's risk tolerance tier (1: Core, 2: Growth, 3: Unrestricted).
     * @param enableElasticity Whether user consents to AI learning and adjusting the radius from past FaceID decisions.
     * @param maxCeiling Absolute hard ceiling the AI can never exceed under any circumstance.
     */
    function initializeAccountPolicy(
        address account,
        address rootOwner,
        uint256 initialRadius,
        uint8 initialRiskTier,
        bool enableElasticity,
        uint256 maxCeiling
    ) public {
        AccountPolicy storage p = policies[account];
        require(p.rootOwner == address(0), "ALREADY_INITIALIZED");
        require(initialRadius > 0, "INVALID_RADIUS");
        require(initialRiskTier >= RISK_TIER_CORE_PRESERVATION && initialRiskTier <= RISK_TIER_UNRESTRICTED, "INVALID_TIER");
        if (enableElasticity) {
            require(maxCeiling >= initialRadius, "CEILING_BELOW_RADIUS");
        }

        p.rootOwner = rootOwner;
        p.tetherRadius = initialRadius;
        p.baselineRadius = initialRadius;
        p.maxElasticCeiling = enableElasticity ? maxCeiling : initialRadius;
        p.riskTier = initialRiskTier;
        p.isDynamicElasticityEnabled = enableElasticity;
        p.currentEpoch = block.timestamp / 1 days;

        emit TetherRadiusConfigured(account, initialRadius, initialRiskTier);
        emit DynamicElasticityToggled(account, enableElasticity, p.maxElasticCeiling);
    }

    /**
     * @notice Overload for backwards compatibility (defaults to static limited mode).
     */
    function initializeAccountPolicy(
        address account,
        address rootOwner,
        uint256 initialRadius,
        uint8 initialRiskTier
    ) external {
        initializeAccountPolicy(account, rootOwner, initialRadius, initialRiskTier, false, initialRadius);
    }

    /**
     * @notice Allows the cognitive AI Agent to dynamically scale The Tether Radius based on historical approved FaceID transactions.
     * @dev Strictly enforces user opt-in, step-up maximums (e.g. max 2.5x current radius), cooldowns, and the hard ceiling.
     * @param account The smart account to adjust.
     * @param proposedRadius The newly proposed Tether Radius (e.g. from 2,000 to 5,000).
     * @param rationale Cryptographic audit rationale explaining the past approved transactions analyzed.
     */
    function autonomousRadiusAdjustment(
        address account,
        uint256 proposedRadius,
        string calldata rationale
    ) external {
        AccountPolicy storage p = policies[account];

        // 1. Caller must be an authorized session key or root owner
        if (!authorizedSessionKeys[account][msg.sender] && msg.sender != p.rootOwner) {
            revert UnauthorizedCaller();
        }

        // 2. Dynamic adjustment must be explicitly enabled by user
        if (!p.isDynamicElasticityEnabled) {
            revert DynamicAdjustmentDisabled();
        }

        // 3. PegGuard circuit breaker must NOT be active
        if (p.emergencyPaused) {
            revert EmergencyCircuitBreakerActive();
        }

        // 4. Proposed radius cannot decrease to 0
        if (proposedRadius == 0) revert InvalidTetherRadius();

        // 5. If increasing, enforce strict harsh step-up rate limits and ceilings
        if (proposedRadius > p.tetherRadius) {
            // Check hard ceiling set by user
            if (proposedRadius > p.maxElasticCeiling) {
                revert ExceedsElasticCeiling(proposedRadius, p.maxElasticCeiling);
            }

            // Check 24-hour cooldown between increases
            if (block.timestamp < p.lastRadiusStepUpTime + CALIBRATION_COOLDOWN) {
                revert StepUpCooldownActive(p.lastRadiusStepUpTime + CALIBRATION_COOLDOWN);
            }

            // Enforce harsh conservatism: strictly max 10% daily increase
            uint256 maxAllowed = p.tetherRadius + (p.tetherRadius * MAX_DAILY_GROWTH_PERCENTAGE) / 100;
            if (proposedRadius > maxAllowed) {
                revert ExcessiveStepUpJump(proposedRadius, maxAllowed);
            }

            p.lastRadiusStepUpTime = block.timestamp;
        }

        uint256 oldRadius = p.tetherRadius;
        p.tetherRadius = proposedRadius;

        emit AutonomousRadiusAdjusted(account, oldRadius, proposedRadius, rationale);
    }

    /**
     * @notice Independent Vault-Native Elasticity Calibration.
     * @dev The Vault autonomously calculates and applies the new Tether Radius directly on-chain,
     *      completely independent of off-chain AI calculation.
     *      Maximum increase is strictly capped at 10% per day.
     *      Requires positive user ratifications and zero active reverts.
     */
    function calibrateDynamicRadius(address account) external returns (uint256 newRadius) {
        AccountPolicy storage p = policies[account];

        // 1. Caller must be an authorized session key, account, or root owner
        if (!authorizedSessionKeys[account][msg.sender] && msg.sender != account && msg.sender != p.rootOwner) {
            revert UnauthorizedCaller();
        }

        // 2. Dynamic adjustment must be explicitly enabled by user
        if (!p.isDynamicElasticityEnabled) {
            revert DynamicAdjustmentDisabled();
        }

        // 3. PegGuard circuit breaker must NOT be active
        if (p.emergencyPaused) {
            revert EmergencyCircuitBreakerActive();
        }

        // 4. Must enforce 24-hour daily calibration cooldown
        if (block.timestamp < p.lastRadiusStepUpTime + CALIBRATION_COOLDOWN) {
            revert StepUpCooldownActive(p.lastRadiusStepUpTime + CALIBRATION_COOLDOWN);
        }

        // 5. Check on-chain review history: requires at least 1 positive ratification
        require(p.consecutiveRatifications > 0, "INSUFFICIENT_RATIFICATIONS");

        // 6. Vault calculates 10% maximum daily growth internally:
        uint256 growth = (p.tetherRadius * MAX_DAILY_GROWTH_PERCENTAGE) / 100;
        uint256 calculated = p.tetherRadius + growth;

        // 7. Enforce hard ceiling
        if (calculated > p.maxElasticCeiling) {
            calculated = p.maxElasticCeiling;
        }

        uint256 oldRadius = p.tetherRadius;
        p.tetherRadius = calculated;
        p.lastRadiusStepUpTime = block.timestamp;
        p.consecutiveRatifications = 0; // reset cycle for next day

        emit AutonomousRadiusAdjusted(
            account,
            oldRadius,
            calculated,
            "Vault-Native Autonomous Calibration (+10% max daily growth based on on-chain ratifications)"
        );

        return calculated;
    }

    /**
     * @notice Toggle dynamic elasticity on/off and update the maximum elastic ceiling.
     */
    function setDynamicElasticity(
        address account,
        bool enabled,
        uint256 maxCeiling
    ) external onlyAccountOrOwner(account) {
        AccountPolicy storage p = policies[account];
        p.isDynamicElasticityEnabled = enabled;
        if (enabled) {
            require(maxCeiling >= p.tetherRadius, "CEILING_BELOW_RADIUS");
            p.maxElasticCeiling = maxCeiling;
        }
        emit DynamicElasticityToggled(account, enabled, p.maxElasticCeiling);
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
     * @dev Enforces The Tether Radius, target whitelist, risk tiers, and the 5-minute Biometric Verification / Sign Approval protocol.
     */
    function preCheck(
        address msgSender,
        uint256 value,
        bytes calldata msgData
    ) external override returns (bytes memory hookData) {
        address account = msg.sender;
        AccountPolicy storage p = policies[account];

        address target = _extractTarget(msgData);
        bytes32 execHash = keccak256(msgData);

        // 1. Roll epoch if 24 hours elapsed
        uint256 currentEpoch = block.timestamp / 1 days;
        if (p.currentEpoch != currentEpoch) {
            p.currentEpoch = currentEpoch;
            p.dailySpent = 0;
        }

        uint256 remainingRadius = p.tetherRadius > p.dailySpent ? p.tetherRadius - p.dailySpent : 0;

        // Determine if this transaction breaks the tether:
        // A breakout occurs if:
        //  (a) spending exceeds remaining daily tether radius, OR
        //  (b) target is not whitelisted and account is not in Tier 3 (Unrestricted), OR
        //  (c) target risk tier exceeds account's risk tier setting.
        bool isBreakout = (value > remainingRadius);
        if (!isBreakout && p.riskTier != RISK_TIER_UNRESTRICTED) {
            if (!whitelistedTargets[account][target] || targetRiskTiers[account][target] > p.riskTier) {
                isBreakout = true;
            }
        }

        // 2. Caller is Root Owner (Passkey / FaceID holder):
        if (msgSender == p.rootOwner) {
            if (isBreakout) {
                // "Breaking the Tether: Not if they are logged in 5alas!"
                // Even the logged-in root owner MUST have an active biometric verification window (within last 5 minutes).
                if (block.timestamp > biometricVerifiedUntil[account]) {
                    revert BiometricVerificationRequired();
                }
                emit TetherBroken(account, p.rootOwner, value, target);
                return abi.encode(true, account, value, target);
            } else {
                // Safe execution within tether radius
                p.dailySpent += value;
                emit TetherRadiusConsumed(account, value, remainingRadius - value, currentEpoch);
                return abi.encode(true, account, value, target);
            }
        }

        // 3. Caller is AI Agent Session Key:
        if (p.emergencyPaused) {
            revert EmergencyCircuitBreakerActive();
        }

        // Explicit user rejection vetoes execution immediately
        if (signRejections[account][execHash]) {
            revert ExecutionRejectedByUser();
        }

        // Check if user provided an explicit Sign Approval for a breakout execution
        if (signApprovals[account][execHash]) {
            // Brain breakout with user sign approval:
            // Must have an active 5-minute biometric verification window
            if (block.timestamp > biometricVerifiedUntil[account]) {
                revert BiometricVerificationRequired();
            }

            // Consume one-time approval to protect against replay
            signApprovals[account][execHash] = false;

            emit TetherBroken(account, msgSender, value, target);
            return abi.encode(true, account, value, target);
        }

        // 4. Normal autonomous AI execution within limits (No Sign Approval):
        // Verify target protocol whitelist & risk tier (Bypassed if Tier 3 Unrestricted is selected)
        if (p.riskTier != RISK_TIER_UNRESTRICTED) {
            if (!whitelistedTargets[account][target]) {
                revert UnauthorizedTarget(target);
            }

            uint8 targetTier = targetRiskTiers[account][target];
            if (targetTier > p.riskTier) {
                revert AssetTierNotPermitted(target, targetTier, p.riskTier);
            }
        }

        // Enforce The Tether Radius (Daily Velocity Limit)
        if (value > remainingRadius) {
            revert TetherRadiusExceeded(value, remainingRadius);
        }

        p.dailySpent += value;
        emit TetherRadiusConsumed(account, value, remainingRadius - value, currentEpoch);

        return abi.encode(false, account, value, target);
    }

    /**
     * @notice ERC-7579 Post-execution Hook callback for WeIdentity audit logs and Morning Review recording.
     */
    function postCheck(bytes calldata hookData) external override {
        // Unpack hookData for telemetry confirmation
        (bool isRoot, address account, uint256 value, address target) = abi.decode(
            hookData,
            (bool, address, uint256, address)
        );
        require(account == msg.sender, "INVALID_POST_ACCOUNT");

        totalAuditedExecutions++;

        // If transaction was done autonomously by the AI Session Key, record it for Morning Review!
        if (!isRoot) {
            executionCount[account]++;
            uint256 recId = executionCount[account];
            executionRecords[account][recId] = AutonomousExecutionRecord({
                id: recId,
                target: target,
                value: value,
                timestamp: block.timestamp,
                status: ReviewStatus.PENDING_REVIEW,
                userNote: ""
            });
            emit AutonomousExecutionLogged(account, recId, target, value, block.timestamp);
        }

        emit PostExecutionAudited(account, isRoot, value, target, totalAuditedExecutions);
    }

    /**
     * @notice Morning Review: User "Likes" / Ratifies an autonomous transaction done while inactive.
     * @dev Replenishes The Tether Radius by the amount of this transaction (since it has explicit user ratification).
     */
    function ratifyTransaction(address account, uint256 recordId) external onlyAccountOrOwner(account) {
        AutonomousExecutionRecord storage rec = executionRecords[account][recordId];
        if (rec.id == 0) revert InvalidRecordId();
        if (rec.status != ReviewStatus.PENDING_REVIEW) revert RecordAlreadyReviewed(rec.status);

        rec.status = ReviewStatus.LIKED_AND_RATIFIED;

        AccountPolicy storage p = policies[account];
        if (p.dailySpent >= rec.value) {
            p.dailySpent -= rec.value;
        } else {
            p.dailySpent = 0;
        }
        p.consecutiveRatifications++; // on-chain endorsement recorded for autonomous calibration

        emit TransactionRatified(account, recordId, rec.value, p.dailySpent);
    }

    /**
     * @notice Morning Review: User rejects / flags an autonomous transaction for cognitive unwind.
     * @dev Marks transaction as REVERT_REQUESTED, contracts the dynamic Tether Radius as a trust penalty.
     */
    function flagTransactionForRevert(address account, uint256 recordId, string calldata reason) external onlyAccountOrOwner(account) {
        AutonomousExecutionRecord storage rec = executionRecords[account][recordId];
        if (rec.id == 0) revert InvalidRecordId();
        if (rec.status != ReviewStatus.PENDING_REVIEW) revert RecordAlreadyReviewed(rec.status);

        rec.status = ReviewStatus.REVERT_REQUESTED;
        rec.userNote = reason;

        AccountPolicy storage p = policies[account];
        p.consecutiveRatifications = 0; // reset consecutive approvals due to rejection

        // Apply trust penalty: cut radius by 20%, but keep above floor (baselineRadius / 2)
        uint256 penalty = (p.tetherRadius * 20) / 100;
        uint256 minFloor = p.baselineRadius / 2;
        if (p.tetherRadius > penalty && p.tetherRadius - penalty >= minFloor) {
            p.tetherRadius -= penalty;
        } else {
            p.tetherRadius = minFloor;
        }

        emit TransactionFlaggedForRevert(account, recordId, reason, p.tetherRadius);
    }

    /**
     * @notice Morning Review: User attaches a feedback note to teach the AI Brain, with optional Brain allowance penalty.
     * @dev The Vault itself is sovereign and NEVER penalized. This penalty only restricts the autonomous AI Brain's
     *      discretionary Tether Radius allowance, leaving all Vault treasury funds and user root capabilities intact.
     */
    function submitTransactionNote(
        address account,
        uint256 recordId,
        string calldata note,
        bool penalizeBrain
    ) external onlyAccountOrOwner(account) {
        AutonomousExecutionRecord storage rec = executionRecords[account][recordId];
        if (rec.id == 0) revert InvalidRecordId();
        if (rec.status != ReviewStatus.PENDING_REVIEW) revert RecordAlreadyReviewed(rec.status);

        rec.status = ReviewStatus.NOTED;
        rec.userNote = note;

        AccountPolicy storage p = policies[account];
        if (penalizeBrain) {
            uint256 penalty = (p.tetherRadius * 10) / 100;
            uint256 minFloor = p.baselineRadius / 2;
            if (p.tetherRadius > penalty && p.tetherRadius - penalty >= minFloor) {
                p.tetherRadius -= penalty;
            } else {
                p.tetherRadius = minFloor;
            }
        }

        emit TransactionNoteSubmitted(account, recordId, note, penalizeBrain, p.tetherRadius);
    }

    /**
     * @notice View an individual autonomous execution record.
     */
    function getExecutionRecord(address account, uint256 recordId) external view returns (AutonomousExecutionRecord memory) {
        return executionRecords[account][recordId];
    }

    /**
     * @notice View all pending review records for the morning review dashboard.
     */
    function getPendingReviews(address account) external view returns (AutonomousExecutionRecord[] memory) {
        uint256 total = executionCount[account];
        uint256 pendingCount = 0;
        for (uint256 i = 1; i <= total; i++) {
            if (executionRecords[account][i].status == ReviewStatus.PENDING_REVIEW) {
                pendingCount++;
            }
        }

        AutonomousExecutionRecord[] memory pending = new AutonomousExecutionRecord[](pendingCount);
        uint256 idx = 0;
        for (uint256 i = 1; i <= total; i++) {
            if (executionRecords[account][i].status == ReviewStatus.PENDING_REVIEW) {
                pending[idx] = executionRecords[account][i];
                idx++;
            }
        }
        return pending;
    }

    /**
     * @notice View complete policy configuration for an account.
     */
    function getAccountPolicy(address account) external view returns (AccountPolicy memory) {
        return policies[account];
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

    // =========================================================================
    // --- Biometric Grace Period & Sign Approval System (Breaking the Tether) ---
    // =========================================================================

    /**
     * @notice Completes biometric verification (FaceID / TouchID / Passkey) when the user is active.
     * @dev Opens an active 5-minute verification grace period. During this window, any
     *      breakout transaction sent by the Brain requires only a simple sign approval
     *      (Normal Accept or Reject), rather than prompting for biometric authentication repeatedly.
     */
    function completeBiometricVerification(address account) external onlyAccountOrOwner(account) {
        uint256 validUntil = block.timestamp + BIOMETRIC_VERIFICATION_WINDOW;
        biometricVerifiedUntil[account] = validUntil;
        emit BiometricVerificationCompleted(account, msg.sender, validUntil);
    }

    /**
     * @notice Explicitly revokes / clears the active biometric verification window (e.g. user locks app).
     */
    function revokeBiometricVerification(address account) external onlyAccountOrOwner(account) {
        biometricVerifiedUntil[account] = 0;
        emit BiometricVerificationRevoked(account);
    }

    /**
     * @notice User provides Sign Approval (Normal Accept or Reject) for a transaction proposed by the Brain.
     * @dev Can only be called while the 5-minute biometric verification window is active.
     *      Does NOT prompt for biometrics—just a standard sign approval confirmation.
     * @param account The smart account.
     * @param executionHash The keccak256 hash of the execution calldata.
     * @param approve True for Accept, False for Reject.
     */
    function submitSignApproval(
        address account,
        bytes32 executionHash,
        bool approve
    ) external onlyAccountOrOwner(account) {
        if (block.timestamp > biometricVerifiedUntil[account]) {
            revert BiometricVerificationRequired();
        }

        if (approve) {
            signApprovals[account][executionHash] = true;
            signRejections[account][executionHash] = false;
        } else {
            signApprovals[account][executionHash] = false;
            signRejections[account][executionHash] = true;
        }

        emit SignApprovalSubmitted(account, executionHash, approve);
    }

    /**
     * @notice Relayed / Gasless Sign Approval with an ECDSA signature from the Root Owner.
     * @dev Allows the user to click Accept or Reject in the UI, generating a simple signature without paying gas.
     */
    function submitSignApprovalWithSignature(
        address account,
        bytes32 executionHash,
        bool approve,
        bytes calldata signature
    ) external {
        if (block.timestamp > biometricVerifiedUntil[account]) {
            revert BiometricVerificationRequired();
        }

        AccountPolicy storage p = policies[account];
        bytes32 messageHash = keccak256(abi.encode(account, executionHash, approve));
        bytes32 ethSignedMessageHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
        address signer = _recoverSigner(ethSignedMessageHash, signature);
        if (signer != p.rootOwner) {
            revert InvalidApprovalSignature();
        }

        if (approve) {
            signApprovals[account][executionHash] = true;
            signRejections[account][executionHash] = false;
        } else {
            signApprovals[account][executionHash] = false;
            signRejections[account][executionHash] = true;
        }

        emit SignApprovalSubmitted(account, executionHash, approve);
    }

    /**
     * @notice Check whether the 5-minute biometric verification window is currently active.
     */
    function isBiometricActive(address account) external view returns (bool) {
        return block.timestamp <= biometricVerifiedUntil[account];
    }

    /**
     * @notice Check approval status for an execution hash.
     */
    function getSignApprovalStatus(address account, bytes32 executionHash) external view returns (bool isApproved, bool isRejected) {
        return (signApprovals[account][executionHash], signRejections[account][executionHash]);
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

    /**
     * @dev Recovers signer from standard Ethereum signed message hash with EIP-2 malleability protection.
     */
    function _recoverSigner(bytes32 ethHash, bytes memory sig) internal pure returns (address) {
        if (sig.length != 65) return address(0);
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := mload(add(sig, 0x20))
            s := mload(add(sig, 0x40))
            v := byte(0, mload(add(sig, 0x60)))
        }
        if (uint256(s) > 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0) {
            return address(0);
        }
        if (v < 27) v += 27;
        if (v != 27 && v != 28) return address(0);
        return ecrecover(ethHash, v, r, s);
    }
}

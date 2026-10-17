// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IERC7579Hook} from "../interfaces/IERC7579Hook.sol";
import {AggregatorV3Interface} from "../interfaces/AggregatorV3Interface.sol";
import {IERC20, IERC20Metadata} from "../interfaces/IERC20.sol";

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

    /// @notice Tier 1: Core Preservation & Mega Assets (BTC, ETH, USDC, USDT, e-CNY, PAXG, Shibor MMFs)
    uint8 public constant RISK_TIER_CORE_PRESERVATION = 1;

    /// @notice Tier 2: Growth & Active DeFi (Liquid Staking stETH/rETH, AMMs, Curve/Uniswap LPs, Yield Vaults)
    uint8 public constant RISK_TIER_GROWTH_DEFI = 2;

    /// @notice Tier 3: Omni-Universe / Unrestricted (Zero whitelist restriction; strictly bound by Tether Radius)
    uint8 public constant RISK_TIER_UNRESTRICTED = 3;

    /// @notice Backwards compatibility alias for Tier 1 Conservative
    uint8 public constant RISK_TIER_CONSERVATIVE = 1;

    /// @notice Backwards compatibility alias for Tier 2 Balanced
    uint8 public constant RISK_TIER_BALANCED = 2;

    /// @notice Backwards compatibility alias for Tier 3 Aggressive
    uint8 public constant RISK_TIER_AGGRESSIVE = 3;

    // --- Dynamic Elasticity Parameters (Axis 2 Learning Engine - Vault-Native) ---

    /// @notice Maximum autonomous daily percentage increase allowed during elasticity calibration (10%)
    uint256 public constant MAX_DAILY_GROWTH_PERCENTAGE = 10;

    /// @notice Minimum cooldown period required between autonomous calibrations (24 hours)
    uint256 public constant CALIBRATION_COOLDOWN = 1 days;

    /// @notice Cooldown alias for backward compatibility
    uint256 public constant STEP_UP_COOLDOWN = 1 days;

    // --- State Storage Per Account ---

    /**
     * @notice Account policy state tracking daily spending velocity, risk tier, and elasticity parameters.
     * @dev Enforces strict ceiling constraints and tracks consecutive ratifications for autonomous calibration.
     */
    struct AccountPolicy {
        uint256 tetherRadius; // Current active daily spending radius
        uint256 baselineRadius; // Initial baseline radius chosen at onboarding
        uint256 maxElasticCeiling; // Absolute hard ceiling the AI can NEVER exceed
        uint256 dailySpent; // Aggregate spent in current 24h epoch
        uint256 currentEpoch; // Current epoch index: block.timestamp / 1 days
        uint8 riskTier; // User's active risk tolerance tier (1, 2, or 3)
        bool isDynamicElasticityEnabled; // User opt-in: Learn from approved decisions (true) vs strictly limited (false)
        uint256 lastRadiusStepUpTime; // Timestamp of last autonomous step-up
        uint256 consecutiveRatifications; // On-chain count of user-ratified transactions without a revert
        address rootOwner; // Passkey WebAuthn FaceID root owner
    }

    /// @notice Mapping from smart account address to its active AccountPolicy configuration
    mapping(address => AccountPolicy) internal policies;

    /// @notice Mapping from account => target contract => authorization status
    mapping(address => mapping(address => bool)) public whitelistedTargets;

    /// @notice Mapping from account => target contract => assigned risk tier (1, 2, or 3)
    mapping(address => mapping(address => uint8)) public targetRiskTiers;

    /// @notice Mapping from account => session key address => authorization status
    mapping(address => mapping(address => bool)) public authorizedSessionKeys;

    // --- Cross-Chain Tether State Synchronization (Multi-Chain Velocity Metering) ---

    /// @notice Cross-chain remote spend per account => epoch => cumulative remote spend (in 8-decimal USD)
    mapping(address => mapping(uint256 => uint256)) public crossChainSpent;

    /// @notice Breakdown by source chain: account => sourceChainId => epoch => spend (in 8-decimal USD)
    mapping(address => mapping(uint256 => mapping(uint256 => uint256))) public chainSpentByEpoch;

    /// @notice Authorized cross-chain sync relayers or bridge adapters
    mapping(address => bool) public authorizedCrossChainRelayers;

    /// @notice Mapping to track used cross-chain sync nonces to prevent double-spending / replay attacks
    mapping(address => mapping(uint256 => bool)) public crossChainNonces;

    /**
     * @notice Cryptographic spend proof for cross-chain velocity synchronization.
     * @param account The smart account whose cross-chain spend is being synchronized.
     * @param sourceChainId The source chain ID where the spending occurred (1, 42161, 2026).
     * @param amountUSD The USD value spent on the remote chain in 8 decimals.
     * @param epoch Daily epoch index (block.timestamp / 1 days).
     * @param nonce Monotonically increasing nonce for replay protection.
     * @param deadline Expiration timestamp for the signature.
     */
    struct CrossChainSpendProof {
        address account;
        uint256 sourceChainId;
        uint256 amountUSD;
        uint256 epoch;
        uint256 nonce;
        uint256 deadline;
    }

    // --- Asynchronous Morning Review System ---

    /**
     * @notice Status lifecycle for an autonomous AI transaction pending user morning review.
     * @dev PENDING_REVIEW: unreviewed; LIKED_AND_RATIFIED: user ratified; REVERT_REQUESTED: flagged; NOTED: user added note.
     */
    enum ReviewStatus {
        PENDING_REVIEW,
        LIKED_AND_RATIFIED,
        REVERT_REQUESTED,
        NOTED
    }

    /**
     * @notice Execution record logged when an autonomous AI session key executes on-chain.
     * @dev Surfaces in the morning review UI for user feedback, ratifications, or cognitive unwinds.
     */
    struct AutonomousExecutionRecord {
        uint256 id;
        address target;
        uint256 value;
        uint256 timestamp;
        ReviewStatus status;
        string userNote;
    }

    /// @notice Total autonomous executions logged per smart account
    mapping(address => uint256) public executionCount;

    /// @notice Execution history per smart account (account => record ID => AutonomousExecutionRecord)
    mapping(address => mapping(uint256 => AutonomousExecutionRecord)) internal executionRecords;

    /// @notice Global counter of all audited executions processed by this hook across all accounts
    uint256 public totalAuditedExecutions;

    // --- 5-Minute Biometric Verification Window & Sign Approval (Breaking the Tether) ---

    /// @notice Active duration for biometric grace period after successful Passkey verification (5 minutes)
    uint256 public constant BIOMETRIC_VERIFICATION_WINDOW = 5 minutes;

    /// @notice Native precompile address for RIP-7212 secp256r1 curve verification
    address public constant RIP7212_PRECOMPILE = address(0x100);

    /// @notice Factory / deployer address allowed to set initial passkey coordinates during onboarding
    address public deployer;

    /// @notice Initializes the hook deployer address
    constructor() {
        deployer = msg.sender;
    }

    /**
     * @notice Hardware WebAuthn P-256 public key coordinates (qx, qy) and registration flag.
     */
    struct WebAuthnPasskey {
        uint256 qx;
        uint256 qy;
        bool isRegistered;
    }

    /// @notice Hardware WebAuthn P-256 Passkey coordinates registered per account
    mapping(address => WebAuthnPasskey) public accountPasskeys;

    /// @notice Gasless sign approval nonces per account for replay protection
    mapping(address => uint256) public signApprovalNonces;

    /// @notice Used biometric challenges per account to prevent replay attacks
    mapping(address => mapping(bytes32 => bool)) public usedBiometricChallenges;

    /// @notice Timestamp until which the account has an active biometric verification window (FaceID/TouchID/Passkey)
    mapping(address => uint256) public biometricVerifiedUntil;

    /// @notice Sign approvals (Accept / Reject) given by the user for executions proposed during active biometric window
    mapping(address => mapping(bytes32 => bool)) public signApprovals;

    /// @notice Expiration timestamp for each sign approval to prevent stale breakout execution
    mapping(address => mapping(bytes32 => uint256)) public signApprovalExpiresAt;

    /// @notice Explicit rejections to prevent rogue execution
    mapping(address => mapping(bytes32 => bool)) public signRejections;

    // --- Dead-Man's Switch & Inactive AI Heartbeat ---

    /// @notice Default timeout for AI agent heartbeat watchdog (48 hours)
    uint256 public constant DEFAULT_AI_HEARTBEAT_TIMEOUT = 48 hours;

    /// @notice Default inactivity threshold before Dead-Man's Switch recovery can be triggered (90 days)
    uint256 public constant DEFAULT_DEADMAN_TIMEOUT = 90 days;

    /// @notice Last timestamp when an AI session key broadcast a heartbeat or executed successfully
    mapping(address => uint256) public lastAIHeartbeat;

    /// @notice Custom heartbeat timeout per account (0 = use DEFAULT_AI_HEARTBEAT_TIMEOUT)
    mapping(address => uint256) public customAIHeartbeatTimeout;

    /// @notice Designated corporate guardian / recovery multisig for Dead-Man's Switch
    mapping(address => address) public deadmanGuardians;

    /// @notice Custom inactivity timeout per account for Dead-Man's Switch (0 = use DEFAULT_DEADMAN_TIMEOUT)
    mapping(address => uint256) public deadmanTimeouts;

    /// @notice Last timestamp when user interacted with the vault (biometrics, sign approval, review, ping)
    mapping(address => uint256) public lastUserActivity;

    // --- Multi-Token & Chainlink Price Feed Oracles (USD Normalized Tether Radius) ---

    /// @notice Sentinel address representing native Ether for Chainlink pricing
    address public constant NATIVE_ETH = 0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE;

    /**
     * @notice Breakdown detail for an individual token held by a smart account.
     * @dev Values are normalized to 8 decimal places conforming to standard Chainlink USD feeds.
     */
    struct TokenBalanceDetail {
        address token;
        string symbol;
        uint8 decimals;
        uint256 balance;
        uint256 priceUSD; // 8 decimals (standard Chainlink USD)
        uint256 valueUSD; // 8 decimals ((balance * priceUSD) / 10^decimals)
    }

    /// @notice Per-account token price feed overrides (account => token => Chainlink AggregatorV3 feed)
    mapping(address => mapping(address => address)) public accountPriceFeeds;

    /// @notice Global default token price feeds (token => Chainlink AggregatorV3 feed)
    mapping(address => address) public globalPriceFeeds;

    // --- Events for WeBank WeIdentity Audit Trails ---

    /**
     * @notice Emitted when an account's spending velocity radius or risk tier is configured or updated.
     * @param account The address of the smart account.
     * @param newRadius The new daily spending limit in native or USD-normalized units.
     * @param riskTier The newly assigned risk tier (1: Core, 2: Growth, 3: Unrestricted).
     */
    event TetherRadiusConfigured(address indexed account, uint256 newRadius, uint8 riskTier);

    /**
     * @notice Emitted when an authorized execution consumes spending allowance within the daily tether radius.
     * @param account The address of the smart account.
     * @param amount The value consumed in this execution.
     * @param remainingRadius The remaining daily spending allowance in the current epoch.
     * @param epoch The current 24-hour epoch index.
     */
    event TetherRadiusConsumed(address indexed account, uint256 amount, uint256 remainingRadius, uint256 epoch);

    /**
     * @notice Emitted when an execution exceeds the daily radius or targets an unwhitelisted asset with biometric approval.
     * @param account The address of the smart account.
     * @param caller The address initiating the execution (root owner or AI session key).
     * @param amount The value of the breakout execution.
     * @param target The target contract address.
     */
    event TetherBroken(address indexed account, address indexed caller, uint256 amount, address indexed target);

    /**
     * @notice Emitted when cross-chain spending is synchronized from a remote chain.
     * @param account The smart account address.
     * @param sourceChainId The chain ID where the spending occurred.
     * @param amount The spend amount in 8-decimal USD.
     * @param newTotalCrossChainSpent The updated cumulative cross-chain spend for this epoch.
     * @param epoch The active 24-hour epoch index.
     */
    event CrossChainSpendSynced(
        address indexed account,
        uint256 indexed sourceChainId,
        uint256 amount,
        uint256 newTotalCrossChainSpent,
        uint256 epoch
    );

    /**
     * @notice Emitted when a cross-chain relayer/bridge address authorization is updated.
     * @param relayer The relayer address.
     * @param status True if authorized, false if revoked.
     */
    event CrossChainRelayerConfigured(address indexed relayer, bool status);

    /**
     * @notice Emitted when a target protocol is added to or removed from an account's whitelist.
     * @param account The address of the smart account.
     * @param target The protocol target contract address.
     * @param riskTier The risk tier assigned to this target (1, 2, or 3).
     * @param status True if whitelisted, false if revoked.
     */
    event TargetWhitelisted(address indexed account, address indexed target, uint8 riskTier, bool status);

    /**
     * @notice Emitted when an AI session key's authorization status is updated for an account.
     * @param account The address of the smart account.
     * @param sessionKey The ephemeral AI agent session key address.
     * @param status True if authorized, false if revoked.
     */
    event SessionKeyAuthorized(address indexed account, address indexed sessionKey, bool status);

    /**
     * @notice Emitted after an execution completes, providing an immutable audit record for WeBank WeIdentity.
     * @param account The address of the smart account.
     * @param isRoot True if initiated by root owner, false if executed autonomously by AI.
     * @param value The value executed in native or normalized units.
     * @param target The target contract address.
     * @param auditIndex The global sequential audit index.
     */
    event PostExecutionAudited(
        address indexed account, bool isRoot, uint256 value, address indexed target, uint256 auditIndex
    );

    /**
     * @notice Emitted when the AI or vault-native calibration engine adjusts the daily tether radius.
     * @param account The address of the smart account.
     * @param previousRadius The spending radius before adjustment.
     * @param newRadius The spending radius after adjustment.
     * @param rationale Cryptographic audit explanation or rationale for the adjustment.
     */
    event AutonomousRadiusAdjusted(
        address indexed account, uint256 previousRadius, uint256 newRadius, string rationale
    );

    /**
     * @notice Emitted when dynamic elasticity is enabled or disabled for an account.
     * @param account The address of the smart account.
     * @param enabled True if dynamic elasticity learning is enabled, false otherwise.
     * @param maxCeiling The absolute upper limit the radius cannot exceed.
     */
    event DynamicElasticityToggled(address indexed account, bool enabled, uint256 maxCeiling);

    /**
     * @notice Emitted when an autonomous AI execution is recorded for the user's morning review dashboard.
     * @param account The address of the smart account.
     * @param recordId Sequential record ID for this execution within the account.
     * @param target The target contract address called.
     * @param value The value executed.
     * @param timestamp The block timestamp of the execution.
     */
    event AutonomousExecutionLogged(
        address indexed account, uint256 indexed recordId, address indexed target, uint256 value, uint256 timestamp
    );

    /**
     * @notice Emitted when the user ratifies ("Likes") an autonomous execution during morning review.
     * @param account The address of the smart account.
     * @param recordId The execution record ID ratified.
     * @param value The amount replenished back into the daily spending radius.
     * @param newDailySpent The updated aggregate daily spent figure.
     */
    event TransactionRatified(address indexed account, uint256 indexed recordId, uint256 value, uint256 newDailySpent);

    /**
     * @notice Emitted when the user flags an autonomous execution for cognitive unwind, applying a trust penalty.
     * @param account The address of the smart account.
     * @param recordId The execution record ID flagged.
     * @param reason The user's feedback or reason for flagging the execution.
     * @param penalizedRadius The contracted tether radius following the 20% trust penalty.
     */
    event TransactionFlaggedForRevert(
        address indexed account, uint256 indexed recordId, string reason, uint256 penalizedRadius
    );

    /**
     * @notice Emitted when the user submits feedback notes for the AI brain with optional velocity allowance reduction.
     * @param account The address of the smart account.
     * @param recordId The execution record ID noted.
     * @param note The user-provided instruction or teaching note.
     * @param penalizeBrain True if a 10% allowance penalty was applied to the AI discretionary allowance.
     * @param resultingRadius The resulting daily spending radius after any penalty.
     */
    event TransactionNoteSubmitted(
        address indexed account, uint256 indexed recordId, string note, bool penalizeBrain, uint256 resultingRadius
    );

    /**
     * @notice Emitted when biometric authentication succeeds, opening the 5-minute grace period window.
     * @param account The address of the smart account.
     * @param verifier The caller that successfully submitted biometric verification.
     * @param validUntil Expiration timestamp for the 5-minute biometric grace window.
     */
    event BiometricVerificationCompleted(address indexed account, address indexed verifier, uint256 validUntil);

    /**
     * @notice Emitted when the active biometric verification window is cleared or revoked.
     * @param account The address of the smart account.
     */
    event BiometricVerificationRevoked(address indexed account);

    /**
     * @notice Emitted when a user submits a sign approval (Accept/Reject) for a proposed breakout execution.
     * @param account The address of the smart account.
     * @param executionHash Keccak256 hash of the execution calldata.
     * @param approved True if approved (Accept), false if rejected (Reject).
     */
    event SignApprovalSubmitted(address indexed account, bytes32 indexed executionHash, bool approved);

    /**
     * @notice Emitted when an AI agent session key records a liveness heartbeat.
     * @param account The address of the smart account.
     * @param sessionKey The session key address broadcasting the heartbeat.
     * @param timestamp The block timestamp when the heartbeat was received.
     */
    event AIHeartbeatRecorded(address indexed account, address indexed sessionKey, uint256 timestamp);

    /**
     * @notice Emitted when the custom AI heartbeat watchdog timeout is configured for an account.
     * @param account The address of the smart account.
     * @param newTimeout The watchdog timeout in seconds (minimum 1 hour).
     */
    event AIHeartbeatTimeoutConfigured(address indexed account, uint256 newTimeout);

    /**
     * @notice Emitted when the Dead-Man's Switch recovery guardian and inactivity timeout are set.
     * @param account The address of the smart account.
     * @param guardian The designated corporate guardian / recovery address.
     * @param timeoutSeconds The inactivity duration required before guardian can trigger recovery.
     */
    event DeadmanSwitchConfigured(address indexed account, address indexed guardian, uint256 timeoutSeconds);

    /**
     * @notice Emitted when the corporate guardian triggers Dead-Man's Switch recovery after extended user inactivity.
     * @param account The address of the smart account.
     * @param guardian The corporate guardian that executed recovery.
     * @param newRootOwner The new root owner address installed on the account.
     * @param timestamp The block timestamp of recovery execution.
     */
    event DeadmanSwitchTriggered(
        address indexed account, address indexed guardian, address newRootOwner, uint256 timestamp
    );

    /**
     * @notice Emitted when user activity is detected or pinged to refresh the Dead-Man's Switch inactivity timer.
     * @param account The address of the smart account.
     * @param timestamp The block timestamp of the activity ping.
     */
    event UserActivityPinged(address indexed account, uint256 timestamp);

    /**
     * @notice Emitted when an account-specific Chainlink oracle price feed override is configured.
     * @param account The address of the smart account.
     * @param token The token address (or NATIVE_ETH sentinel).
     * @param feed The Chainlink AggregatorV3 price feed contract address.
     */
    event AccountPriceFeedConfigured(address indexed account, address indexed token, address indexed feed);

    /**
     * @notice Emitted when a default global Chainlink oracle price feed is configured.
     * @param token The token address (or NATIVE_ETH sentinel).
     * @param feed The Chainlink AggregatorV3 price feed contract address.
     */
    event GlobalPriceFeedConfigured(address indexed token, address indexed feed);

    /**
     * @notice Emitted when WebAuthn P-256 Passkey hardware public key coordinates are registered for an account.
     * @param account The address of the smart account.
     * @param qx The P-256 public key affine X coordinate.
     * @param qy The P-256 public key affine Y coordinate.
     */
    event PasskeyConfigured(address indexed account, uint256 qx, uint256 qy);

    // --- Custom Errors ---

    /// @notice Reverted when an execution attempt exceeds the remaining daily spending allowance without breakout authorization.
    /// @param attempted The attempted spending amount.
    /// @param remainingRadius The remaining daily allowance in the current epoch.
    error TetherRadiusExceeded(uint256 attempted, uint256 remainingRadius);

    /// @notice Reverted when an AI session key attempts to interact with an unwhitelisted contract or the guard hook itself.
    /// @param target The unauthorized target contract address.
    error UnauthorizedTarget(address target);

    /// @notice Reverted when the target contract's risk tier exceeds the account's configured risk tier threshold.
    /// @param target The target contract address.
    /// @param targetTier The risk tier classification of the target contract.
    /// @param allowedTier The maximum risk tier permitted by the account's policy.
    error AssetTierNotPermitted(address target, uint8 targetTier, uint8 allowedTier);

    /// @notice Reverted when an unauthorized address attempts an administrative or restricted action.
    error UnauthorizedCaller();

    /// @notice Reverted when an invalid tether radius (e.g., zero) is specified.
    error InvalidTetherRadius();

    /// @notice Reverted when autonomous radius adjustment is called on an account without dynamic elasticity enabled.
    error DynamicAdjustmentDisabled();

    /// @notice Reverted when proposed radius adjustment exceeds the user's hard elastic ceiling.
    /// @param proposed The proposed new radius.
    /// @param maxCeiling The configured hard maximum elastic ceiling.
    error ExceedsElasticCeiling(uint256 proposed, uint256 maxCeiling);

    /// @notice Reverted when radius adjustment is attempted before the 24-hour step-up cooldown expires.
    /// @param nextEligibleTime The timestamp when the next adjustment is permitted.
    error StepUpCooldownActive(uint256 nextEligibleTime);

    /// @notice Reverted when an autonomous step-up exceeds the maximum allowed daily growth rate (10%).
    /// @param proposed The proposed new radius.
    /// @param maxAllowed The maximum radius permitted under the 10% daily limit.
    error ExcessiveStepUpJump(uint256 proposed, uint256 maxAllowed);

    /// @notice Reverted when referencing a non-existent autonomous execution record ID.
    error InvalidRecordId();

    /// @notice Reverted when attempting to review an execution record that is not in PENDING_REVIEW status.
    /// @param currentStatus The existing review status of the record.
    error RecordAlreadyReviewed(ReviewStatus currentStatus);

    /// @notice Reverted when a breakout transaction is attempted without an active 5-minute biometric grace period.
    error BiometricVerificationRequired();

    /// @notice Reverted when breakout execution requires explicit sign approval from the root owner.
    error SignApprovalRequired();

    /// @notice Reverted when an execution attempt matches an explicit user rejection hash.
    error ExecutionRejectedByUser();

    /// @notice Reverted when a gasless sign approval ECDSA signature fails verification against the root owner.
    error InvalidApprovalSignature();

    /// @notice Reverted when an AI session key attempts execution after the heartbeat watchdog timeout has elapsed.
    /// @param lastBeat The timestamp of the last recorded heartbeat.
    /// @param currentTime The current block timestamp.
    error AIHeartbeatStale(uint256 lastBeat, uint256 currentTime);

    /// @notice Reverted when Dead-Man's Switch recovery is triggered before the required inactivity period has elapsed.
    /// @param lastActivity The timestamp of last detected user activity.
    /// @param eligibleTime The earliest timestamp when Dead-Man's recovery can be executed.
    error DeadmanSwitchNotEligible(uint256 lastActivity, uint256 eligibleTime);

    /// @notice Reverted when an address other than the designated corporate guardian attempts Dead-Man's Switch recovery.
    error UnauthorizedGuardian();

    /// @notice Reverted when RIP-7212 P-256 precompile verification fails for a passkey signature.
    error InvalidP256Signature();

    /// @notice Reverted when a Chainlink price feed returns a non-positive price answer.
    /// @param token The token address queried.
    /// @param price The invalid price returned by the oracle.
    error InvalidOraclePrice(address token, int256 price);

    /// @notice Reverted when a Chainlink price feed returns data older than the staleness threshold.
    /// @param token The token address queried.
    /// @param updatedAt The timestamp when the price was last updated by Chainlink.
    error StaleOraclePrice(address token, uint256 updatedAt);

    /// @notice Reverted when USD-normalized pricing is required for a token with no configured price feed.
    /// @param token The token address lacking a Chainlink price feed.
    error MissingOraclePriceFeed(address token);

    /// @notice Reverted when P-256 verification coordinates do not match the account's registered passkey.
    error UnauthorizedPasskey();

    /// @notice Reverted when a signature is submitted after its expiration deadline.
    error ExpiredSignature();

    /// @notice Reverted when a biometric challenge is reused, protecting against replay attacks.
    error ChallengeAlreadyUsed();

    function _checkAccountOrOwner(address account) internal view {
        if (msg.sender != account && msg.sender != policies[account].rootOwner) {
            revert UnauthorizedCaller();
        }
    }

    /**
     * @notice Restricts execution to either the smart account itself or its registered root owner passkey address.
     * @param account The smart account whose policy is being accessed or modified.
     */
    modifier onlyAccountOrOwner(address account) {
        _checkAccountOrOwner(account);
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
        require(msg.sender == account || msg.sender == deployer, "UNAUTHORIZED_INIT");
        require(initialRadius > 0, "INVALID_RADIUS");
        require(
            initialRiskTier >= RISK_TIER_CORE_PRESERVATION && initialRiskTier <= RISK_TIER_UNRESTRICTED, "INVALID_TIER"
        );
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
     * @param account The address of the smart account.
     * @param rootOwner The Passkey / WebAuthn root owner address.
     * @param initialRadius The initial daily spending tether radius.
     * @param initialRiskTier The user's risk tolerance tier (1: Core, 2: Growth, 3: Unrestricted).
     */
    function initializeAccountPolicy(address account, address rootOwner, uint256 initialRadius, uint8 initialRiskTier)
        external
    {
        initializeAccountPolicy(account, rootOwner, initialRadius, initialRiskTier, false, initialRadius);
    }

    /**
     * @notice Allows the cognitive AI Agent to dynamically scale The Tether Radius based on historical approved FaceID transactions.
     * @dev Strictly enforces user opt-in, step-up maximums (e.g. max 2.5x current radius), cooldowns, and the hard ceiling.
     * @param account The smart account to adjust.
     * @param proposedRadius The newly proposed Tether Radius (e.g. from 2,000 to 5,000).
     * @param rationale Cryptographic audit rationale explaining the past approved transactions analyzed.
     */
    function autonomousRadiusAdjustment(address account, uint256 proposedRadius, string calldata rationale) external {
        AccountPolicy storage p = policies[account];

        // 1. Caller must be an authorized session key or root owner
        if (!authorizedSessionKeys[account][msg.sender] && msg.sender != p.rootOwner) {
            revert UnauthorizedCaller();
        }

        // 2. Dynamic adjustment must be explicitly enabled by user
        if (!p.isDynamicElasticityEnabled) {
            revert DynamicAdjustmentDisabled();
        }

        // 3. Proposed radius cannot decrease to 0
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
     * @param account The smart account to calibrate.
     * @return newRadius The newly computed and updated daily Tether Radius.
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

        // 3. Must enforce 24-hour daily calibration cooldown
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
     * @param account The address of the smart account.
     * @param enabled True to enable autonomous elasticity calibration, false to enforce static limits.
     * @param maxCeiling The absolute upper limit the radius can never exceed.
     */
    function setDynamicElasticity(address account, bool enabled, uint256 maxCeiling)
        external
        onlyAccountOrOwner(account)
    {
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
     * @param account The address of the smart account.
     * @param newRadius The newly configured daily spending radius.
     * @param newRiskTier The newly assigned risk tolerance tier (1, 2, or 3).
     */
    function setTetherRadius(address account, uint256 newRadius, uint8 newRiskTier)
        external
        onlyAccountOrOwner(account)
    {
        if (newRadius == 0) revert InvalidTetherRadius();
        require(newRiskTier >= RISK_TIER_CONSERVATIVE && newRiskTier <= RISK_TIER_AGGRESSIVE, "INVALID_TIER");

        AccountPolicy storage p = policies[account];
        p.tetherRadius = newRadius;
        p.riskTier = newRiskTier;

        emit TetherRadiusConfigured(account, newRadius, newRiskTier);
    }

    /**
     * @notice Whitelists an on-chain protocol and sets its risk tier rating.
     * @param account The address of the smart account.
     * @param target The target contract address to whitelist or modify.
     * @param status True to allow interactions, false to revoke.
     * @param tier The risk tier classification for this target contract.
     */
    function setTargetWhitelist(address account, address target, bool status, uint8 tier)
        external
        onlyAccountOrOwner(account)
    {
        whitelistedTargets[account][target] = status;
        targetRiskTiers[account][target] = tier;

        emit TargetWhitelisted(account, target, tier, status);
    }

    /**
     * @notice Authorizes or revokes an ephemeral AI Agent session key.
     * @param account The address of the smart account.
     * @param sessionKey The ephemeral AI session key address.
     * @param status True to authorize, false to revoke.
     */
    function setSessionKeyAuthorization(address account, address sessionKey, bool status)
        external
        onlyAccountOrOwner(account)
    {
        authorizedSessionKeys[account][sessionKey] = status;
        emit SessionKeyAuthorized(account, sessionKey, status);
    }

    // =========================================================================
    // --- Multi-Token & Chainlink Price Feed Oracles (USD Normalized Tether) ---
    // =========================================================================

    /**
     * @notice Configures a per-account Chainlink price feed override for a token or NATIVE_ETH.
     * @param account The address of the smart account.
     * @param token The token address (or NATIVE_ETH sentinel).
     * @param feed The Chainlink AggregatorV3 price feed contract address.
     */
    function setAccountPriceFeed(address account, address token, address feed) external onlyAccountOrOwner(account) {
        accountPriceFeeds[account][token] = feed;
        emit AccountPriceFeedConfigured(account, token, feed);
    }

    /**
     * @notice Configures a global default Chainlink price feed for a token or NATIVE_ETH.
     * @param token The token address (or NATIVE_ETH sentinel).
     * @param feed The Chainlink AggregatorV3 price feed contract address.
     */
    function setGlobalPriceFeed(address token, address feed) external {
        if (msg.sender != deployer || deployer == address(0)) {
            revert UnauthorizedCaller();
        }
        globalPriceFeeds[token] = feed;
        emit GlobalPriceFeedConfigured(token, feed);
    }

    /**
     * @notice Resolves active price feed for an account and token (account override > global default).
     * @param account The address of the smart account.
     * @param token The token address queried.
     * @return feed The resolved AggregatorV3 price feed address (or address(0) if none).
     */
    function getPriceFeed(address account, address token) public view returns (address) {
        address feed = accountPriceFeeds[account][token];
        if (feed != address(0)) return feed;
        return globalPriceFeeds[token];
    }

    /**
     * @notice Fetches the latest USD price (8 decimals) and feed decimals from the configured Chainlink oracle.
     * @dev Validates price freshness (< 24h) and non-negative answer.
     * @param account The address of the smart account.
     * @param token The token address queried (or NATIVE_ETH sentinel).
     * @return priceUSD The latest asset price normalized to Chainlink feed decimals.
     * @return feedDecimals The number of decimals reported by the Chainlink aggregator.
     */
    function getLatestPrice(address account, address token) public view returns (uint256 priceUSD, uint8 feedDecimals) {
        address feed = getPriceFeed(account, token);
        require(feed != address(0), "PRICE_FEED_NOT_FOUND");

        (uint80 roundId, int256 answer,, uint256 updatedAt, uint80 answeredInRound) =
            AggregatorV3Interface(feed).latestRoundData();
        if (answer <= 0) {
            revert InvalidOraclePrice(token, answer);
        }
        if (updatedAt == 0 || answeredInRound < roundId) {
            revert StaleOraclePrice(token, updatedAt);
        }
        if (block.timestamp > updatedAt && block.timestamp - updatedAt > 1 days) {
            revert StaleOraclePrice(token, updatedAt);
        }

        uint8 dec = AggregatorV3Interface(feed).decimals();
        return (uint256(answer), dec);
    }

    /**
     * @notice Computes normalized 8-decimal USD value for a given token balance and oracle price.
     * @dev Internal helper accounting for both token decimals and oracle feed decimals.
     * @param amount The token balance or transaction amount.
     * @param tokenDecimals The decimal places of the underlying token (e.g. 18 for WETH, 6 for USDC).
     * @param priceUSD The price fetched from Chainlink.
     * @param feedDecimals The decimal places of the Chainlink feed (typically 8).
     * @return val The calculated value normalized strictly to 8 decimal places.
     */
    function _calculateUSD(uint256 amount, uint8 tokenDecimals, uint256 priceUSD, uint8 feedDecimals)
        internal
        pure
        returns (uint256)
    {
        if (amount == 0 || priceUSD == 0) return 0;
        uint256 val = (amount * priceUSD) / (10 ** tokenDecimals);
        if (feedDecimals != 8 && feedDecimals > 0) {
            if (feedDecimals > 8) {
                val = val / (10 ** (feedDecimals - 8));
            } else {
                val = val * (10 ** (8 - feedDecimals));
            }
        }
        return val;
    }

    /**
     * @notice Performs a fault-tolerant oracle lookup for portfolio views without reverting on oracle failure.
     * @dev Internal view helper returning zeros if feed is missing, negative, or stale.
     * @param account The address of the smart account.
     * @param token The token address to query.
     * @return priceUSD The reported oracle price (0 if query fails).
     * @return feedDecimals The oracle decimals (0 if query fails).
     */
    function _safeGetPrice(address account, address token)
        internal
        view
        returns (uint256 priceUSD, uint8 feedDecimals)
    {
        address feed = getPriceFeed(account, token);
        if (feed == address(0)) return (0, 0);

        try AggregatorV3Interface(feed).latestRoundData() returns (
            uint80 roundId, int256 answer, uint256, uint256 updatedAt, uint80 answeredInRound
        ) {
            if (answer <= 0 || updatedAt == 0 || answeredInRound < roundId) return (0, 0);
            if (block.timestamp > updatedAt && block.timestamp - updatedAt > 1 days) return (0, 0);
            uint8 dec = 8;
            try AggregatorV3Interface(feed).decimals() returns (uint8 d) {
                dec = d;
            } catch {}
            return (uint256(answer), dec);
        } catch {
            return (0, 0);
        }
    }

    /**
     * @notice Inspects call calldata to extract token transfers (ERC-20 transfer, approve, transferFrom)
     *         and normalizes the value into 8-decimal USD via Chainlink Price Feeds.
     * @dev If feeds are configured, returns the total USD value of the call.
     *      If no feeds are configured, falls back to raw nativeValue/tokenAmount for backwards compatibility.
     * @param account The address of the smart account.
     * @param target The target contract address being executed.
     * @param nativeValue The native Ether value accompanying the transaction.
     * @param msgData The execution calldata payload.
     * @return effectiveAmount The computed effective value (USD 8-decimal or raw units).
     * @return isUSD True if value was calculated using Chainlink USD price feeds, false otherwise.
     */
    function calculateCallUSDValue(address account, address target, uint256 nativeValue, bytes calldata msgData)
        public
        view
        returns (uint256 effectiveAmount, bool isUSD)
    {
        address ethFeed = getPriceFeed(account, NATIVE_ETH);
        uint256 nativeUSD = 0;
        bool hasFeed = false;

        if (nativeValue > 0) {
            if (ethFeed != address(0)) {
                (uint256 ethPrice, uint8 ethFeedDec) = getLatestPrice(account, NATIVE_ETH);
                nativeUSD = _calculateUSD(nativeValue, 18, ethPrice, ethFeedDec);
                hasFeed = true;
            }
        }

        // Inspect inner calldata for ERC-20 method calls
        // In TecAccount execution format, msgData is: target (20) || nativeValue (32) || callData (variable)
        uint256 tokenAmount = 0;
        if (msgData.length >= 56) {
            bytes4 selector = bytes4(msgData[52:56]);

            // transfer(address to, uint256 amount) - 0xa9059cbb
            // approve(address spender, uint256 amount) - 0x095ea7b3
            // increaseAllowance(address spender, uint256 addedValue) - 0x39509351
            if ((selector == 0xa9059cbb || selector == 0x095ea7b3 || selector == 0x39509351) && msgData.length >= 120) {
                tokenAmount = abi.decode(msgData[88:120], (uint256));
            }
            // transferFrom(address from, address to, uint256 amount) - 0x23b872dd
            else if (selector == 0x23b872dd && msgData.length >= 152) {
                tokenAmount = abi.decode(msgData[120:152], (uint256));
            }
        }

        if (tokenAmount > 0) {
            address tokenFeed = getPriceFeed(account, target);
            if (tokenFeed != address(0)) {
                (uint256 tokenPrice, uint8 tokenFeedDec) = getLatestPrice(account, target);
                uint8 tokDec = 18;
                try IERC20Metadata(target).decimals() returns (uint8 d) {
                    tokDec = d;
                } catch {}

                uint256 erc20USD = _calculateUSD(tokenAmount, tokDec, tokenPrice, tokenFeedDec);
                return (nativeUSD + erc20USD, true);
            } else if (ethFeed != address(0)) {
                // Account is operating with USD oracles, but this token has no price feed configured!
                revert MissingOraclePriceFeed(target);
            } else {
                // Legacy non-oracle mode: return raw tokenAmount if nativeValue == 0, else nativeValue + tokenAmount
                return (nativeValue > 0 ? nativeValue : tokenAmount, false);
            }
        }

        if (hasFeed) {
            return (nativeUSD, true);
        }

        return (nativeValue, false);
    }

    /**
     * @notice Comprehensive Portfolio Valuation: Returns total account portfolio value in USD (8 decimals)
     *         and full breakdown for all queried assets (ETH + ERC-20 tokens).
     * @param account The Tec-C Smart Account address.
     * @param tokens Array of token addresses to inspect (can include NATIVE_ETH or address(0) for ETH).
     * @return totalValueUSD Total portfolio valuation in 8-decimal USD.
     * @return details Array of TokenBalanceDetail structs with balances, prices, and USD values.
     */
    function getTotalPortfolioValueUSD(address account, address[] calldata tokens)
        external
        view
        returns (uint256 totalValueUSD, TokenBalanceDetail[] memory details)
    {
        details = new TokenBalanceDetail[](tokens.length);

        for (uint256 i = 0; i < tokens.length; i++) {
            address token = tokens[i];
            if (token == address(0) || token == NATIVE_ETH) {
                uint256 bal = account.balance;
                (uint256 price, uint8 feedDec) = _safeGetPrice(account, NATIVE_ETH);
                uint256 val = _calculateUSD(bal, 18, price, feedDec);

                details[i] = TokenBalanceDetail({
                    token: NATIVE_ETH, symbol: "ETH", decimals: 18, balance: bal, priceUSD: price, valueUSD: val
                });
                totalValueUSD += val;
            } else {
                uint256 bal = 0;
                try IERC20(token).balanceOf(account) returns (uint256 b) {
                    bal = b;
                } catch {}

                string memory sym = "TOKEN";
                try IERC20Metadata(token).symbol() returns (string memory s) {
                    sym = s;
                } catch {}

                uint8 dec = 18;
                try IERC20Metadata(token).decimals() returns (uint8 d) {
                    dec = d;
                } catch {}

                (uint256 price, uint8 feedDec) = _safeGetPrice(account, token);
                uint256 val = _calculateUSD(bal, dec, price, feedDec);

                details[i] = TokenBalanceDetail({
                    token: token, symbol: sym, decimals: dec, balance: bal, priceUSD: price, valueUSD: val
                });
                totalValueUSD += val;
            }
        }
    }

    /**
     * @notice Helper to compute remaining radius for an account in the given epoch.
     */
    function _getAccountRemaining(address account, AccountPolicy storage p, uint256 epoch)
        internal
        view
        returns (uint256)
    {
        uint256 localSpent = (p.currentEpoch == epoch) ? p.dailySpent : 0;
        uint256 total = localSpent + crossChainSpent[account][epoch];
        return p.tetherRadius > total ? p.tetherRadius - total : 0;
    }

    /**
     * @notice ERC-7579 Pre-execution Hook verification.
     * @dev Enforces The Tether Radius, target whitelist, risk tiers, and the 5-minute Biometric Verification / Sign Approval protocol.
     * @param msgSender The address of the caller initiating execution on the smart account.
     * @param value The amount of native Ether transferred with the execution call.
     * @param msgData The execution calldata payload (ERC-7579 execution format).
     * @return hookData Contextual byte payload passed forward to postCheck callback.
     */
    function preCheck(address msgSender, uint256 value, bytes calldata msgData)
        external
        override
        returns (bytes memory hookData)
    {
        address account = msg.sender;
        AccountPolicy storage p = policies[account];

        address target = _extractTarget(msgData);
        bytes32 execHash = keccak256(msgData);

        // VULN-01 Defense: Autonomous AI session keys cannot target the security hook itself!
        if (msgSender != p.rootOwner && target == address(this)) {
            revert UnauthorizedTarget(target);
        }

        // 1. Roll epoch if 24 hours elapsed
        uint256 currentEpoch = block.timestamp / 1 days;
        if (p.currentEpoch != currentEpoch) {
            p.currentEpoch = currentEpoch;
            p.dailySpent = 0;
        }

        uint256 remainingRadius = _getAccountRemaining(account, p, currentEpoch);

        // Calculate USD Normalized effective amount (ERC-20 and/or Native ETH via Chainlink)
        (uint256 effectiveAmount,) = calculateCallUSDValue(account, target, value, msgData);

        // Determine if this transaction breaks the tether:
        // A breakout occurs if:
        //  (a) spending exceeds remaining daily tether radius, OR
        //  (b) target is not whitelisted and account is not in Tier 3 (Unrestricted), OR
        //  (c) target risk tier exceeds account's risk tier setting.
        bool isBreakout = (effectiveAmount > remainingRadius)
            || (p.riskTier != RISK_TIER_UNRESTRICTED
                && (!whitelistedTargets[account][target] || targetRiskTiers[account][target] > p.riskTier));

        // 2. Caller is Root Owner (Passkey / FaceID holder):
        if (msgSender == p.rootOwner) {
            lastUserActivity[account] = block.timestamp;
            if (isBreakout) {
                // Breaking the Tether: Active biometric verification required (5-minute window)
                if (block.timestamp > biometricVerifiedUntil[account]) {
                    revert BiometricVerificationRequired();
                }
                emit TetherBroken(account, p.rootOwner, effectiveAmount, target);
                return abi.encode(true, account, effectiveAmount, target);
            } else {
                // Safe execution within tether radius
                p.dailySpent += effectiveAmount;
                emit TetherRadiusConsumed(
                    account, effectiveAmount, _getAccountRemaining(account, p, currentEpoch), currentEpoch
                );
                return abi.encode(true, account, effectiveAmount, target);
            }
        }

        // 3. Caller is AI Agent Session Key:
        // Enforce Inactive AI Heartbeat Watchdog:
        {
            uint256 hb = customAIHeartbeatTimeout[account];
            if (hb == 0) hb = DEFAULT_AI_HEARTBEAT_TIMEOUT;
            if (lastAIHeartbeat[account] > 0 && block.timestamp > lastAIHeartbeat[account] + hb) {
                revert AIHeartbeatStale(lastAIHeartbeat[account], block.timestamp);
            }
        }
        lastAIHeartbeat[account] = block.timestamp;

        // Explicit user rejection vetoes execution immediately
        if (signRejections[account][execHash]) {
            revert ExecutionRejectedByUser();
        }

        // Check if user provided an explicit Sign Approval for a breakout execution
        if (signApprovals[account][execHash]) {
            // Brain breakout with user sign approval:
            if (
                block.timestamp > signApprovalExpiresAt[account][execHash]
                    || block.timestamp > biometricVerifiedUntil[account]
            ) {
                delete signApprovals[account][execHash];
                delete signApprovalExpiresAt[account][execHash];
                revert BiometricVerificationRequired();
            }

            // Consume one-time approval to protect against replay
            signApprovals[account][execHash] = false;
            delete signApprovalExpiresAt[account][execHash];

            emit TetherBroken(account, msgSender, effectiveAmount, target);
            return abi.encode(true, account, effectiveAmount, target);
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

        // Enforce The Tether Radius (Daily Velocity Limit across all chains)
        if (effectiveAmount > remainingRadius) {
            revert TetherRadiusExceeded(effectiveAmount, remainingRadius);
        }

        p.dailySpent += effectiveAmount;
        emit TetherRadiusConsumed(
            account, effectiveAmount, _getAccountRemaining(account, p, currentEpoch), currentEpoch
        );

        return abi.encode(false, account, effectiveAmount, target);
    }

    /**
     * @notice ERC-7579 Post-execution Hook callback for WeIdentity audit logs and Morning Review recording.
     * @dev Automatically parses hookData and logs autonomous executions for asynchronous morning review.
     * @param hookData The byte payload returned from preCheck containing execution context.
     */
    function postCheck(bytes calldata hookData) external override {
        // Unpack hookData for telemetry confirmation
        (bool isRoot, address account, uint256 value, address target) =
            abi.decode(hookData, (bool, address, uint256, address));
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

    function _getPendingRecord(address account, uint256 recordId)
        internal
        view
        returns (AutonomousExecutionRecord storage rec)
    {
        rec = executionRecords[account][recordId];
        if (rec.id == 0) revert InvalidRecordId();
        if (rec.status != ReviewStatus.PENDING_REVIEW) revert RecordAlreadyReviewed(rec.status);
    }

    function _applyRadiusPenalty(AccountPolicy storage p, uint256 pct) internal {
        uint256 penalty = (p.tetherRadius * pct) / 100;
        uint256 targetRadius = (p.tetherRadius > penalty) ? p.tetherRadius - penalty : 0;
        uint256 minFloor = p.baselineRadius / 2;
        p.tetherRadius = (p.tetherRadius > minFloor && targetRadius < minFloor) ? minFloor : targetRadius;
    }

    /**
     * @notice Morning Review: User "Likes" / Ratifies an autonomous transaction done while inactive.
     * @dev Replenishes The Tether Radius by the amount of this transaction (since it has explicit user ratification).
     * @param account The address of the smart account.
     * @param recordId The unique ID of the autonomous execution record to ratify.
     */
    function ratifyTransaction(address account, uint256 recordId) external onlyAccountOrOwner(account) {
        AutonomousExecutionRecord storage rec = _getPendingRecord(account, recordId);
        rec.status = ReviewStatus.LIKED_AND_RATIFIED;

        AccountPolicy storage p = policies[account];
        uint256 currentEpoch = block.timestamp / 1 days;
        if (p.currentEpoch != currentEpoch) {
            p.currentEpoch = currentEpoch;
            p.dailySpent = 0;
        } else if (rec.timestamp / 1 days == currentEpoch) {
            p.dailySpent = p.dailySpent >= rec.value ? p.dailySpent - rec.value : 0;
        }
        p.consecutiveRatifications++;

        emit TransactionRatified(account, recordId, rec.value, p.dailySpent);
    }

    /**
     * @notice Morning Review: User rejects / flags an autonomous transaction for cognitive unwind.
     * @dev Marks transaction as REVERT_REQUESTED, contracts the dynamic Tether Radius as a trust penalty.
     * @param account The address of the smart account.
     * @param recordId The unique ID of the autonomous execution record to flag.
     * @param reason The user's feedback or rationale for flagging the transaction.
     */
    function flagTransactionForRevert(address account, uint256 recordId, string calldata reason)
        external
        onlyAccountOrOwner(account)
    {
        AutonomousExecutionRecord storage rec = _getPendingRecord(account, recordId);
        rec.status = ReviewStatus.REVERT_REQUESTED;
        rec.userNote = reason;

        AccountPolicy storage p = policies[account];
        p.consecutiveRatifications = 0;
        _applyRadiusPenalty(p, 20);

        emit TransactionFlaggedForRevert(account, recordId, reason, p.tetherRadius);
    }

    /**
     * @notice Morning Review: User attaches a feedback note to teach the AI Brain, with optional Brain allowance penalty.
     * @dev The Vault itself is sovereign and NEVER penalized. This penalty only restricts the autonomous AI Brain's
     *      discretionary Tether Radius allowance, leaving all Vault treasury funds and user root capabilities intact.
     * @param account The address of the smart account.
     * @param recordId The unique ID of the autonomous execution record being annotated.
     * @param note Explanatory feedback or guidance text for future autonomous transactions.
     * @param penalizeBrain True to reduce the autonomous spending allowance by 10%, false to keep radius unchanged.
     */
    function submitTransactionNote(address account, uint256 recordId, string calldata note, bool penalizeBrain)
        external
        onlyAccountOrOwner(account)
    {
        AutonomousExecutionRecord storage rec = _getPendingRecord(account, recordId);
        rec.status = ReviewStatus.NOTED;
        rec.userNote = note;

        AccountPolicy storage p = policies[account];
        if (penalizeBrain) {
            _applyRadiusPenalty(p, 10);
        }

        emit TransactionNoteSubmitted(account, recordId, note, penalizeBrain, p.tetherRadius);
    }

    /**
     * @notice View an individual autonomous execution record.
     * @param account The address of the smart account.
     * @param recordId The unique ID of the execution record.
     * @return The AutonomousExecutionRecord struct.
     */
    function getExecutionRecord(address account, uint256 recordId)
        external
        view
        returns (AutonomousExecutionRecord memory)
    {
        return executionRecords[account][recordId];
    }

    /**
     * @notice View all pending review records for the morning review dashboard.
     * @param account The address of the smart account.
     * @return pending An array of AutonomousExecutionRecord structs currently in PENDING_REVIEW status.
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
     * @param account The address of the smart account.
     * @return The AccountPolicy struct containing current parameters.
     */
    function getAccountPolicy(address account) external view returns (AccountPolicy memory) {
        return policies[account];
    }

    /**
     * @notice View remaining spending radius in current 24h epoch.
     * @param account The address of the smart account.
     * @return The remaining spending allowance for the current epoch.
     */
    function getRemainingRadius(address account) external view returns (uint256) {
        return _getAccountRemaining(account, policies[account], block.timestamp / 1 days);
    }

    // =========================================================================
    // --- Cross-Chain Tether State Synchronization (Multi-Chain Velocity) ---
    // =========================================================================

    function _applyCrossChainSpend(address account, uint256 sourceChainId, uint256 amountUSD, uint256 epoch) internal {
        require(amountUSD > 0, "INVALID_AMOUNT");
        chainSpentByEpoch[account][sourceChainId][epoch] += amountUSD;
        crossChainSpent[account][epoch] += amountUSD;
        emit CrossChainSpendSynced(account, sourceChainId, amountUSD, crossChainSpent[account][epoch], epoch);
    }

    /**
     * @notice Authorizes or revokes a cross-chain relayer/bridge contract.
     * @param relayer The address of the relayer or bridge.
     * @param status True to authorize, false to revoke.
     */
    function setCrossChainRelayer(address relayer, bool status) external {
        require(msg.sender == deployer, "ONLY_DEPLOYER");
        authorizedCrossChainRelayers[relayer] = status;
        emit CrossChainRelayerConfigured(relayer, status);
    }

    /**
     * @notice Synchronizes spend from another chain into this hook's active epoch.
     * @dev Enforces the Cross-Chain Tether Radius so spending on Chain A immediately reduces available quota on Chain B and C.
     * @param account The smart account whose cross-chain spend is being synchronized.
     * @param sourceChainId The chain ID where the spending occurred (e.g. 1 for Ethereum, 42161 for Arbitrum, 2026 for FISCO BCOS).
     * @param amountUSD The USD value spent on the remote chain (normalized in 8 decimals).
     * @param epoch The epoch index (block.timestamp / 1 days).
     */
    function syncCrossChainSpend(address account, uint256 sourceChainId, uint256 amountUSD, uint256 epoch) external {
        AccountPolicy storage p = policies[account];
        require(p.rootOwner != address(0), "ACCOUNT_NOT_INITIALIZED");
        require(
            msg.sender == account || msg.sender == p.rootOwner || authorizedSessionKeys[account][msg.sender]
                || authorizedCrossChainRelayers[msg.sender],
            "UNAUTHORIZED_CROSS_CHAIN_SYNC"
        );
        _applyCrossChainSpend(account, sourceChainId, amountUSD, epoch);
    }

    /**
     * @notice Synchronizes cross-chain spend using an ECDSA signature from the root owner or session key.
     * @dev Allows trustless, decentralized relaying of cross-chain spend proofs across EVM and consortium chains.
     * @param proof The cross-chain spend proof struct containing account, sourceChainId, amountUSD, epoch, nonce, and deadline.
     * @param signature Cryptographic ECDSA signature from rootOwner or authorized session key.
     */
    function syncCrossChainSpendWithSignature(CrossChainSpendProof calldata proof, bytes calldata signature) external {
        AccountPolicy storage p = policies[proof.account];
        require(p.rootOwner != address(0), "ACCOUNT_NOT_INITIALIZED");
        require(block.timestamp <= proof.deadline, "SIGNATURE_EXPIRED");
        require(!crossChainNonces[proof.account][proof.nonce], "NONCE_ALREADY_USED");
        crossChainNonces[proof.account][proof.nonce] = true;

        bytes32 messageHash = keccak256(
            abi.encode(
                proof.account,
                proof.sourceChainId,
                proof.amountUSD,
                proof.epoch,
                proof.nonce,
                proof.deadline,
                block.chainid,
                address(this)
            )
        );
        bytes32 ethSignedMessageHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
        address signer = _recoverSigner(ethSignedMessageHash, signature);
        require(signer == p.rootOwner || authorizedSessionKeys[proof.account][signer], "INVALID_CROSS_CHAIN_SIGNER");
        _applyCrossChainSpend(proof.account, proof.sourceChainId, proof.amountUSD, proof.epoch);
    }

    /**
     * @notice Computes total cross-chain spend across local and all remote chains in the current epoch.
     * @param account The smart account.
     * @return totalSpent The aggregate spend across all chains in 8-decimal USD.
     * @return remainingRadius The remaining spend capacity before the tether radius is exhausted.
     */
    function getCrossChainSpendingState(address account)
        external
        view
        returns (uint256 totalSpent, uint256 remainingRadius)
    {
        AccountPolicy storage p = policies[account];
        uint256 currentEpoch = block.timestamp / 1 days;
        uint256 localSpent = (p.currentEpoch == currentEpoch) ? p.dailySpent : 0;
        totalSpent = localSpent + crossChainSpent[account][currentEpoch];
        remainingRadius = p.tetherRadius > totalSpent ? p.tetherRadius - totalSpent : 0;
    }

    // =========================================================================
    // --- Biometric Grace Period & Sign Approval System (Breaking the Tether) ---
    // =========================================================================

    function _recordSignApproval(address account, bytes32 executionHash, bool approve) internal {
        lastUserActivity[account] = block.timestamp;
        if (approve) {
            signApprovals[account][executionHash] = true;
            signRejections[account][executionHash] = false;
            uint256 windowEnd = biometricVerifiedUntil[account];
            uint256 minGrace = block.timestamp + 60 seconds;
            signApprovalExpiresAt[account][executionHash] = windowEnd > minGrace ? windowEnd : minGrace;
        } else {
            signApprovals[account][executionHash] = false;
            signRejections[account][executionHash] = true;
            delete signApprovalExpiresAt[account][executionHash];
        }
        emit SignApprovalSubmitted(account, executionHash, approve);
    }

    /**
     * @notice Completes biometric verification (FaceID / TouchID / Passkey) when the user is active.
     * @param account The address of the smart account.
     */
    function completeBiometricVerification(address account) external onlyAccountOrOwner(account) {
        uint256 validUntil = block.timestamp + BIOMETRIC_VERIFICATION_WINDOW;
        biometricVerifiedUntil[account] = validUntil;
        lastUserActivity[account] = block.timestamp;
        emit BiometricVerificationCompleted(account, msg.sender, validUntil);
    }

    /**
     * @notice Explicitly revokes / clears the active biometric verification window (e.g. user locks app).
     * @param account The address of the smart account.
     */
    function revokeBiometricVerification(address account) external onlyAccountOrOwner(account) {
        biometricVerifiedUntil[account] = 0;
        emit BiometricVerificationRevoked(account);
    }

    /**
     * @notice User provides Sign Approval (Normal Accept or Reject) for a transaction proposed by the Brain.
     * @param account The smart account.
     * @param executionHash The keccak256 hash of the execution calldata.
     * @param approve True for Accept, False for Reject.
     */
    function submitSignApproval(address account, bytes32 executionHash, bool approve)
        external
        onlyAccountOrOwner(account)
    {
        if (block.timestamp > biometricVerifiedUntil[account]) {
            revert BiometricVerificationRequired();
        }
        _recordSignApproval(account, executionHash, approve);
    }

    /**
     * @notice Relayed / Gasless Sign Approval with an ECDSA signature from the Root Owner.
     * @param account The smart account address.
     * @param executionHash The keccak256 hash of the target execution calldata.
     * @param approve True to approve, false to reject.
     * @param deadline Expiration timestamp for the gasless signature.
     * @param signature Cryptographic ECDSA signature from the root owner.
     */
    function submitSignApprovalWithSignature(
        address account,
        bytes32 executionHash,
        bool approve,
        uint256 deadline,
        bytes calldata signature
    ) public {
        if (block.timestamp > deadline) {
            revert ExpiredSignature();
        }
        if (block.timestamp > biometricVerifiedUntil[account]) {
            revert BiometricVerificationRequired();
        }

        AccountPolicy storage p = policies[account];
        bytes32 messageHash = keccak256(
            abi.encode(
                account, executionHash, approve, signApprovalNonces[account]++, deadline, block.chainid, address(this)
            )
        );
        bytes32 ethSignedMessageHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
        address signer = _recoverSigner(ethSignedMessageHash, signature);
        if (signer != p.rootOwner) {
            revert InvalidApprovalSignature();
        }

        _recordSignApproval(account, executionHash, approve);
    }

    /**
     * @notice Check whether the 5-minute biometric verification window is currently active.
     * @param account The address of the smart account.
     * @return True if the biometric window is active, false otherwise.
     */
    function isBiometricActive(address account) external view returns (bool) {
        return block.timestamp <= biometricVerifiedUntil[account];
    }

    /**
     * @notice Check approval status for an execution hash.
     * @param account The address of the smart account.
     * @param executionHash The keccak256 hash of the execution calldata.
     * @return isApproved True if explicitly approved by user.
     * @return isRejected True if explicitly rejected by user.
     */
    function getSignApprovalStatus(address account, bytes32 executionHash)
        external
        view
        returns (bool isApproved, bool isRejected)
    {
        return (signApprovals[account][executionHash], signRejections[account][executionHash]);
    }

    // =========================================================================
    // --- Dead-Man's Switch & Inactive AI Heartbeat Engine ---
    // =========================================================================

    /**
     * @notice Broadcasts an AI liveness heartbeat from an authorized session key.
     * @param account The address of the smart account.
     */
    function recordAIHeartbeat(address account) external {
        if (
            !authorizedSessionKeys[account][msg.sender] && msg.sender != account
                && msg.sender != policies[account].rootOwner
        ) {
            revert UnauthorizedCaller();
        }
        lastAIHeartbeat[account] = block.timestamp;
        emit AIHeartbeatRecorded(account, msg.sender, block.timestamp);
    }

    /**
     * @notice Configures custom AI heartbeat timeout (e.g. 24 hours, 48 hours).
     * @param account The address of the smart account.
     * @param timeoutSeconds The timeout threshold in seconds (minimum 1 hour).
     */
    function configureAIHeartbeatTimeout(address account, uint256 timeoutSeconds) external onlyAccountOrOwner(account) {
        require(timeoutSeconds >= 1 hours, "TIMEOUT_TOO_SHORT");
        customAIHeartbeatTimeout[account] = timeoutSeconds;
        emit AIHeartbeatTimeoutConfigured(account, timeoutSeconds);
    }

    /**
     * @notice Configures Dead-Man's Switch guardian and inactivity threshold.
     * @param account The address of the smart account.
     * @param guardian The designated corporate guardian / recovery multisig.
     * @param timeoutSeconds Inactivity threshold in seconds (0 = defaults to 90 days).
     */
    function configureDeadmanSwitch(address account, address guardian, uint256 timeoutSeconds)
        external
        onlyAccountOrOwner(account)
    {
        require(guardian != address(0), "INVALID_GUARDIAN");
        deadmanGuardians[account] = guardian;
        deadmanTimeouts[account] = timeoutSeconds > 0 ? timeoutSeconds : DEFAULT_DEADMAN_TIMEOUT;
        if (lastUserActivity[account] == 0) {
            lastUserActivity[account] = block.timestamp;
        }
        emit DeadmanSwitchConfigured(account, guardian, deadmanTimeouts[account]);
    }

    /**
     * @notice Pings user activity to reset Dead-Man's Switch timer.
     * @param account The address of the smart account.
     */
    function pingUserActivity(address account) external onlyAccountOrOwner(account) {
        lastUserActivity[account] = block.timestamp;
        emit UserActivityPinged(account, block.timestamp);
    }

    /**
     * @notice Triggers Dead-Man's Switch recovery after user has been inactive for the designated timeout.
     * @dev Rotates the Root Owner to a designated corporate guardian / successor, restoring vault sovereignty.
     * @param account The address of the smart account.
     * @param newRootOwner The replacement root owner address to install.
     */
    function triggerDeadmanRecovery(address account, address newRootOwner) external {
        if (msg.sender != deadmanGuardians[account]) {
            revert UnauthorizedGuardian();
        }
        require(newRootOwner != address(0), "INVALID_NEW_OWNER");

        uint256 timeout = deadmanTimeouts[account] > 0 ? deadmanTimeouts[account] : DEFAULT_DEADMAN_TIMEOUT;
        uint256 eligibleTime = lastUserActivity[account] + timeout;
        if (lastUserActivity[account] == 0 || block.timestamp < eligibleTime) {
            revert DeadmanSwitchNotEligible(lastUserActivity[account], eligibleTime);
        }

        AccountPolicy storage p = policies[account];
        p.rootOwner = newRootOwner;
        lastUserActivity[account] = block.timestamp;

        emit DeadmanSwitchTriggered(account, msg.sender, newRootOwner, block.timestamp);
    }

    /**
     * @notice View helper to check if AI Heartbeat is currently healthy.
     * @param account The address of the smart account.
     * @return True if heartbeat is active within the timeout window, false if stale.
     */
    function isAIHeartbeatAlive(address account) external view returns (bool) {
        if (lastAIHeartbeat[account] == 0) return true;
        uint256 timeout =
            customAIHeartbeatTimeout[account] > 0 ? customAIHeartbeatTimeout[account] : DEFAULT_AI_HEARTBEAT_TIMEOUT;
        return block.timestamp <= lastAIHeartbeat[account] + timeout;
    }

    /**
     * @notice View helper to check if Dead-Man's Switch is currently triggerable by the guardian.
     * @param account The address of the smart account.
     * @return True if user inactivity period has elapsed and guardian can trigger recovery.
     */
    function isDeadmanSwitchTriggerable(address account) external view returns (bool) {
        if (deadmanGuardians[account] == address(0) || lastUserActivity[account] == 0) return false;
        uint256 timeout = deadmanTimeouts[account] > 0 ? deadmanTimeouts[account] : DEFAULT_DEADMAN_TIMEOUT;
        return block.timestamp >= lastUserActivity[account] + timeout;
    }

    // =========================================================================
    // --- WebAuthn P-256 (RIP-7212) Native Precompile Biometric Verification ---
    // =========================================================================

    /**
     * @notice Configures the WebAuthn P-256 Passkey coordinates (qx, qy) for an account.
     * @dev Allows deployer to register initial coordinates during onboarding if not yet registered.
     * @param account The address of the smart account.
     * @param qx Affine X coordinate of the user's secp256r1 public key.
     * @param qy Affine Y coordinate of the user's secp256r1 public key.
     */
    function setAccountPasskey(address account, uint256 qx, uint256 qy) external {
        if (msg.sender != account && msg.sender != policies[account].rootOwner) {
            if (msg.sender != deployer || accountPasskeys[account].isRegistered) {
                revert UnauthorizedCaller();
            }
        }
        require(qx != 0 && qy != 0, "INVALID_COORDINATES");
        accountPasskeys[account] = WebAuthnPasskey({qx: qx, qy: qy, isRegistered: true});
        emit PasskeyConfigured(account, qx, qy);
    }

    /**
     * @notice Verifies a WebAuthn P-256 FaceID / TouchID signature via RIP-7212 precompile at 0x100.
     * @dev Opens the 5-minute Biometric Verification window upon successful hardware verification.
     *      Coordinates (qx, qy) must strictly match the account's registered passkey.
     *      SEC-01: Enforces deadline and tracks challenge replay protection.
     * @param account The address of the smart account.
     * @param messageHash The signed challenge digest.
     * @param r Signature r value.
     * @param s Signature s value (normalized).
     * @param qx Public key X coordinate.
     * @param qy Public key Y coordinate.
     * @param deadline Expiration timestamp for the biometric challenge.
     */
    function completeBiometricVerificationWithP256(
        address account,
        bytes32 messageHash,
        uint256 r,
        uint256 s,
        uint256 qx,
        uint256 qy,
        uint256 deadline
    ) public {
        if (block.timestamp > deadline) {
            revert ExpiredSignature();
        }
        if (usedBiometricChallenges[account][messageHash]) {
            revert ChallengeAlreadyUsed();
        }

        // Enforce that public key coordinates strictly match registered passkey for this account
        WebAuthnPasskey storage pk = accountPasskeys[account];
        if (!pk.isRegistered || pk.qx != qx || pk.qy != qy) {
            revert UnauthorizedPasskey();
        }

        // 1. Verify P-256 signature via native RIP-7212 precompile at 0x100
        bytes memory input = abi.encode(messageHash, r, s, qx, qy);
        (bool success, bytes memory output) = RIP7212_PRECOMPILE.staticcall(input);
        if (!success || output.length != 32 || abi.decode(output, (uint256)) != 1) {
            revert InvalidP256Signature();
        }

        // Mark challenge as consumed to prevent replay attacks
        usedBiometricChallenges[account][messageHash] = true;

        // 2. Open 5-minute Biometric Verification Window
        uint256 validUntil = block.timestamp + BIOMETRIC_VERIFICATION_WINDOW;
        biometricVerifiedUntil[account] = validUntil;
        lastUserActivity[account] = block.timestamp;

        emit BiometricVerificationCompleted(account, msg.sender, validUntil);
    }

    /**
     * @notice Backward-compatible overload for WebAuthn P-256 biometric verification.
     * @param account The address of the smart account.
     * @param messageHash The signed challenge digest.
     * @param r Signature r value.
     * @param s Signature s value.
     * @param qx Public key X coordinate.
     * @param qy Public key Y coordinate.
     */
    function completeBiometricVerificationWithP256(
        address account,
        bytes32 messageHash,
        uint256 r,
        uint256 s,
        uint256 qx,
        uint256 qy
    ) external {
        completeBiometricVerificationWithP256(
            account, messageHash, r, s, qx, qy, block.timestamp + BIOMETRIC_VERIFICATION_WINDOW
        );
    }

    /**
     * @notice Extracts the destination target from execution calldata.
     * @dev In standard ERC-7579 execution encoding, the first 20 bytes contain the target address.
     * @param msgData The raw execution calldata.
     * @return target The extracted target contract address (or address(0) if data is shorter than 20 bytes).
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
     * @notice Recovers signer from standard Ethereum signed message hash with EIP-2 malleability protection.
     * @dev Validates s value to prevent signature malleability attacks.
     * @param ethHash The 32-byte Ethereum signed message hash.
     * @param sig The 65-byte ECDSA signature (r, s, v).
     * @return The recovered address, or address(0) if recovery fails or signature is malleable.
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

// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import { IERC7579Hook } from "../interfaces/IERC7579Hook.sol";
import { AggregatorV3Interface } from "../interfaces/AggregatorV3Interface.sol";
import { IERC20, IERC20Metadata } from "../interfaces/IERC20.sol";

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
    address public constant RIP7212_PRECOMPILE = address(0x100);
    address public deployer;

    constructor() {
        deployer = msg.sender;
    }

    struct WebAuthnPasskey {
        uint256 qx;
        uint256 qy;
        bool isRegistered;
    }

    /// @notice Hardware WebAuthn P-256 Passkey coordinates registered per account
    mapping(address => WebAuthnPasskey) public accountPasskeys;

    /// @notice Gasless sign approval nonces per account for replay protection
    mapping(address => uint256) public signApprovalNonces;

    /// @notice Timestamp until which the account has an active biometric verification window (FaceID/TouchID/Passkey)
    mapping(address => uint256) public biometricVerifiedUntil;

    /// @notice Sign approvals (Accept / Reject) given by the user for executions proposed during active biometric window
    mapping(address => mapping(bytes32 => bool)) public signApprovals;

    /// @notice Explicit rejections to prevent rogue execution
    mapping(address => mapping(bytes32 => bool)) public signRejections;

    // --- Dead-Man's Switch & Inactive AI Heartbeat ---
    uint256 public constant DEFAULT_AI_HEARTBEAT_TIMEOUT = 48 hours;
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
    address public constant NATIVE_ETH = 0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE;

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
    event TetherRadiusConfigured(address indexed account, uint256 newRadius, uint8 riskTier);
    event TetherRadiusConsumed(address indexed account, uint256 amount, uint256 remainingRadius, uint256 epoch);
    event TetherBroken(address indexed account, address indexed caller, uint256 amount, address indexed target);
    event TargetWhitelisted(address indexed account, address indexed target, uint8 riskTier, bool status);
    event SessionKeyAuthorized(address indexed account, address indexed sessionKey, bool status);
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
    event AIHeartbeatRecorded(address indexed account, address indexed sessionKey, uint256 timestamp);
    event AIHeartbeatTimeoutConfigured(address indexed account, uint256 newTimeout);
    event DeadmanSwitchConfigured(address indexed account, address indexed guardian, uint256 timeoutSeconds);
    event DeadmanSwitchTriggered(address indexed account, address indexed guardian, address newRootOwner, uint256 timestamp);
    event UserActivityPinged(address indexed account, uint256 timestamp);
    event AccountPriceFeedConfigured(address indexed account, address indexed token, address indexed feed);
    event GlobalPriceFeedConfigured(address indexed token, address indexed feed);
    event PasskeyConfigured(address indexed account, uint256 qx, uint256 qy);

    // --- Custom Errors ---
    error TetherRadiusExceeded(uint256 attempted, uint256 remainingRadius);
    error UnauthorizedTarget(address target);
    error AssetTierNotPermitted(address target, uint8 targetTier, uint8 allowedTier);
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
    error AIHeartbeatStale(uint256 lastBeat, uint256 currentTime);
    error DeadmanSwitchNotEligible(uint256 lastActivity, uint256 eligibleTime);
    error UnauthorizedGuardian();
    error InvalidP256Signature();
    error InvalidOraclePrice(address token, int256 price);
    error StaleOraclePrice(address token, uint256 updatedAt);
    error MissingOraclePriceFeed(address token);
    error UnauthorizedPasskey();
    error ExpiredSignature();

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
        require(
            msg.sender == account || msg.sender == deployer,
            "UNAUTHORIZED_INIT"
        );
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



    // =========================================================================
    // --- Multi-Token & Chainlink Price Feed Oracles (USD Normalized Tether) ---
    // =========================================================================

    /**
     * @notice Configures a per-account Chainlink price feed override for a token or NATIVE_ETH.
     */
    function setAccountPriceFeed(
        address account,
        address token,
        address feed
    ) external onlyAccountOrOwner(account) {
        accountPriceFeeds[account][token] = feed;
        emit AccountPriceFeedConfigured(account, token, feed);
    }

    /**
     * @notice Configures a global default Chainlink price feed for a token or NATIVE_ETH.
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
     */
    function getPriceFeed(address account, address token) public view returns (address) {
        address feed = accountPriceFeeds[account][token];
        if (feed != address(0)) return feed;
        return globalPriceFeeds[token];
    }

    /**
     * @notice Fetches the latest USD price (8 decimals) and feed decimals from the configured Chainlink oracle.
     * @dev Validates price freshness (< 24h) and non-negative answer.
     */
    function getLatestPrice(address account, address token) public view returns (uint256 priceUSD, uint8 feedDecimals) {
        address feed = getPriceFeed(account, token);
        require(feed != address(0), "PRICE_FEED_NOT_FOUND");

        (, int256 answer, , uint256 updatedAt, ) = AggregatorV3Interface(feed).latestRoundData();
        if (answer <= 0) {
            revert InvalidOraclePrice(token, answer);
        }
        if (block.timestamp > updatedAt && block.timestamp - updatedAt > 1 days) {
            revert StaleOraclePrice(token, updatedAt);
        }

        uint8 dec = AggregatorV3Interface(feed).decimals();
        return (uint256(answer), dec);
    }

    /**
     * @dev Internal helper to calculate USD value normalized to 8 decimals.
     */
    function _calculateUSD(
        uint256 amount,
        uint8 tokenDecimals,
        uint256 priceUSD,
        uint8 feedDecimals
    ) internal pure returns (uint256) {
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
     * @dev Safe oracle lookup helper for read-only portfolio views without reverting.
     */
    function _safeGetPrice(address account, address token) internal view returns (uint256 priceUSD, uint8 feedDecimals) {
        address feed = getPriceFeed(account, token);
        if (feed == address(0)) return (0, 0);

        try AggregatorV3Interface(feed).latestRoundData() returns (
            uint80,
            int256 answer,
            uint256,
            uint256 updatedAt,
            uint80
        ) {
            if (answer <= 0) return (0, 0);
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
     */
    function calculateCallUSDValue(
        address account,
        address target,
        uint256 nativeValue,
        bytes calldata msgData
    ) public view returns (uint256 effectiveAmount, bool isUSD) {
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
    function getTotalPortfolioValueUSD(
        address account,
        address[] calldata tokens
    ) external view returns (uint256 totalValueUSD, TokenBalanceDetail[] memory details) {
        details = new TokenBalanceDetail[](tokens.length);

        for (uint256 i = 0; i < tokens.length; i++) {
            address token = tokens[i];
            if (token == address(0) || token == NATIVE_ETH) {
                uint256 bal = account.balance;
                (uint256 price, uint8 feedDec) = _safeGetPrice(account, NATIVE_ETH);
                uint256 val = _calculateUSD(bal, 18, price, feedDec);

                details[i] = TokenBalanceDetail({
                    token: NATIVE_ETH,
                    symbol: "ETH",
                    decimals: 18,
                    balance: bal,
                    priceUSD: price,
                    valueUSD: val
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
                    token: token,
                    symbol: sym,
                    decimals: dec,
                    balance: bal,
                    priceUSD: price,
                    valueUSD: val
                });
                totalValueUSD += val;
            }
        }
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

        // Calculate USD Normalized effective amount (ERC-20 and/or Native ETH via Chainlink)
        (uint256 effectiveAmount, ) = calculateCallUSDValue(account, target, value, msgData);

        // Determine if this transaction breaks the tether:
        // A breakout occurs if:
        //  (a) spending exceeds remaining daily tether radius, OR
        //  (b) target is not whitelisted and account is not in Tier 3 (Unrestricted), OR
        //  (c) target risk tier exceeds account's risk tier setting.
        bool isBreakout = (effectiveAmount > remainingRadius);
        if (!isBreakout && p.riskTier != RISK_TIER_UNRESTRICTED) {
            if (!whitelistedTargets[account][target] || targetRiskTiers[account][target] > p.riskTier) {
                isBreakout = true;
            }
        }

        // 2. Caller is Root Owner (Passkey / FaceID holder):
        if (msgSender == p.rootOwner) {
            lastUserActivity[account] = block.timestamp;
            if (isBreakout) {
                // "Breaking the Tether: Not if they are logged in 5alas!"
                // Even the logged-in root owner MUST have an active biometric verification window (within last 5 minutes).
                if (block.timestamp > biometricVerifiedUntil[account]) {
                    revert BiometricVerificationRequired();
                }
                emit TetherBroken(account, p.rootOwner, effectiveAmount, target);
                return abi.encode(true, account, effectiveAmount, target);
            } else {
                // Safe execution within tether radius
                p.dailySpent += effectiveAmount;
                emit TetherRadiusConsumed(account, effectiveAmount, remainingRadius - effectiveAmount, currentEpoch);
                return abi.encode(true, account, effectiveAmount, target);
            }
        }

        // 3. Caller is AI Agent Session Key:
        // Enforce Inactive AI Heartbeat Watchdog:
        uint256 hbTimeout = customAIHeartbeatTimeout[account] > 0 ? customAIHeartbeatTimeout[account] : DEFAULT_AI_HEARTBEAT_TIMEOUT;
        if (lastAIHeartbeat[account] > 0 && block.timestamp > lastAIHeartbeat[account] + hbTimeout) {
            revert AIHeartbeatStale(lastAIHeartbeat[account], block.timestamp);
        }
        lastAIHeartbeat[account] = block.timestamp;

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

        // Enforce The Tether Radius (Daily Velocity Limit)
        if (effectiveAmount > remainingRadius) {
            revert TetherRadiusExceeded(effectiveAmount, remainingRadius);
        }

        p.dailySpent += effectiveAmount;
        emit TetherRadiusConsumed(account, effectiveAmount, remainingRadius - effectiveAmount, currentEpoch);

        return abi.encode(false, account, effectiveAmount, target);
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
        uint256 currentEpoch = block.timestamp / 1 days;
        if (p.currentEpoch != currentEpoch) {
            p.currentEpoch = currentEpoch;
            p.dailySpent = 0;
        } else if (rec.timestamp / 1 days == currentEpoch) {
            if (p.dailySpent >= rec.value) {
                p.dailySpent -= rec.value;
            } else {
                p.dailySpent = 0;
            }
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
        lastUserActivity[account] = block.timestamp;
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

        lastUserActivity[account] = block.timestamp;

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
     * @dev Protected with nonce, deadline, and chainId to prevent signature replay and cross-chain attacks.
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
            abi.encode(account, executionHash, approve, signApprovalNonces[account]++, deadline, block.chainid)
        );
        bytes32 ethSignedMessageHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
        address signer = _recoverSigner(ethSignedMessageHash, signature);
        if (signer != p.rootOwner) {
            revert InvalidApprovalSignature();
        }

        lastUserActivity[account] = block.timestamp;

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

    // =========================================================================
    // --- Dead-Man's Switch & Inactive AI Heartbeat Engine ---
    // =========================================================================

    /**
     * @notice Broadcasts an AI liveness heartbeat from an authorized session key.
     */
    function recordAIHeartbeat(address account) external {
        if (!authorizedSessionKeys[account][msg.sender] && msg.sender != account && msg.sender != policies[account].rootOwner) {
            revert UnauthorizedCaller();
        }
        lastAIHeartbeat[account] = block.timestamp;
        emit AIHeartbeatRecorded(account, msg.sender, block.timestamp);
    }

    /**
     * @notice Configures custom AI heartbeat timeout (e.g. 24 hours, 48 hours).
     */
    function configureAIHeartbeatTimeout(address account, uint256 timeoutSeconds) external onlyAccountOrOwner(account) {
        require(timeoutSeconds >= 1 hours, "TIMEOUT_TOO_SHORT");
        customAIHeartbeatTimeout[account] = timeoutSeconds;
        emit AIHeartbeatTimeoutConfigured(account, timeoutSeconds);
    }

    /**
     * @notice Configures Dead-Man's Switch guardian and inactivity threshold.
     */
    function configureDeadmanSwitch(
        address account,
        address guardian,
        uint256 timeoutSeconds
    ) external onlyAccountOrOwner(account) {
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
     */
    function pingUserActivity(address account) external onlyAccountOrOwner(account) {
        lastUserActivity[account] = block.timestamp;
        emit UserActivityPinged(account, block.timestamp);
    }

    /**
     * @notice Triggers Dead-Man's Switch recovery after user has been inactive for the designated timeout.
     * @dev Rotates the Root Owner to a designated corporate guardian / successor, restoring vault sovereignty.
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
     */
    function isAIHeartbeatAlive(address account) external view returns (bool) {
        if (lastAIHeartbeat[account] == 0) return true;
        uint256 timeout = customAIHeartbeatTimeout[account] > 0 ? customAIHeartbeatTimeout[account] : DEFAULT_AI_HEARTBEAT_TIMEOUT;
        return block.timestamp <= lastAIHeartbeat[account] + timeout;
    }

    /**
     * @notice View helper to check if Dead-Man's Switch is currently triggerable by the guardian.
     */
    function isDeadmanSwitchTriggerable(address account) external view returns (bool) {
        if (deadmanGuardians[account] == address(0) || lastUserActivity[account] == 0) return false;
        uint256 timeout = deadmanTimeouts[account] > 0 ? deadmanTimeouts[account] : DEFAULT_DEADMAN_TIMEOUT;
        return block.timestamp > lastUserActivity[account] + timeout;
    }

    // =========================================================================
    // --- WebAuthn P-256 (RIP-7212) Native Precompile Biometric Verification ---
    // =========================================================================

    /**
     * @notice Configures the WebAuthn P-256 Passkey coordinates (qx, qy) for an account.
     */
    function setAccountPasskey(
        address account,
        uint256 qx,
        uint256 qy
    ) external onlyAccountOrOwner(account) {
        require(qx != 0 && qy != 0, "INVALID_COORDINATES");
        accountPasskeys[account] = WebAuthnPasskey({
            qx: qx,
            qy: qy,
            isRegistered: true
        });
        emit PasskeyConfigured(account, qx, qy);
    }

    /**
     * @notice Verifies a WebAuthn P-256 FaceID / TouchID signature via RIP-7212 precompile at 0x100.
     * @dev Opens the 5-minute Biometric Verification window upon successful hardware verification.
     *      Coordinates (qx, qy) must strictly match the account's registered passkey.
     */
    function completeBiometricVerificationWithP256(
        address account,
        bytes32 messageHash,
        uint256 r,
        uint256 s,
        uint256 qx,
        uint256 qy
    ) external {
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

        // 2. Open 5-minute Biometric Verification Window
        uint256 validUntil = block.timestamp + BIOMETRIC_VERIFICATION_WINDOW;
        biometricVerifiedUntil[account] = validUntil;
        lastUserActivity[account] = block.timestamp;

        emit BiometricVerificationCompleted(account, msg.sender, validUntil);
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

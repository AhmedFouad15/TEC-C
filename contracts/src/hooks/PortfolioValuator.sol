// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IERC20, IERC20Metadata} from "../interfaces/IERC20.sol";
import {AggregatorV3Interface} from "../interfaces/AggregatorV3Interface.sol";
import {TetherGuardHook} from "./TetherGuardHook.sol";

/**
 * @title PortfolioValuator
 * @author Tec-C Core Engineering Team
 * @notice Helper contract offloading price feed valuation, morning reviews, and signature validation from TetherGuardHook.
 */
contract PortfolioValuator {
    address internal constant NATIVE_ETH = 0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE;

    // --- Autonomous Execution History (Morning Review) ---
    mapping(address => uint256) public executionCount;
    mapping(address => mapping(uint256 => TetherGuardHook.AutonomousExecutionRecord)) public executionRecords;

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

    function _safeGetPrice(address hook, address account, address token)
        internal
        view
        returns (uint256 priceUSD, uint8 feedDecimals)
    {
        address feed = TetherGuardHook(hook).getPriceFeed(account, token);
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

    function _getNativeUSD(address hook, address account, uint256 nativeValue)
        internal
        view
        returns (uint256 nativeUSD, bool hasFeed)
    {
        if (nativeValue == 0) return (0, false);
        address ethFeed = TetherGuardHook(hook).getPriceFeed(account, NATIVE_ETH);
        if (ethFeed == address(0)) return (0, false);
        (uint256 ethPrice, uint8 ethFeedDec) = TetherGuardHook(hook).getLatestPrice(account, NATIVE_ETH);
        return (_calculateUSD(nativeValue, 18, ethPrice, ethFeedDec), true);
    }

    function _extractTokenAmount(bytes calldata msgData) internal pure returns (uint256) {
        if (msgData.length < 56) return 0;
        bytes4 selector = bytes4(msgData[52:56]);
        if ((selector == 0xa9059cbb || selector == 0x095ea7b3 || selector == 0x39509351) && msgData.length >= 120) {
            return abi.decode(msgData[88:120], (uint256));
        } else if (selector == 0x23b872dd && msgData.length >= 152) {
            return abi.decode(msgData[120:152], (uint256));
        }
        return 0;
    }

    function _extractERC20USD(address hook, address account, address target, uint256 tokenAmount)
        internal
        view
        returns (uint256 erc20USD, bool hasTokenFeed)
    {
        address tokenFeed = TetherGuardHook(hook).getPriceFeed(account, target);
        if (tokenFeed != address(0)) {
            (uint256 tokenPrice, uint8 tokenFeedDec) = TetherGuardHook(hook).getLatestPrice(account, target);
            uint8 tokDec = 18;
            try IERC20Metadata(target).decimals() returns (uint8 d) {
                tokDec = d;
            } catch {}
            return (_calculateUSD(tokenAmount, tokDec, tokenPrice, tokenFeedDec), true);
        }
        return (0, false);
    }

    function calculateCallUSDValue(
        address account,
        address target,
        uint256 nativeValue,
        bytes calldata msgData,
        address hook
    ) external view returns (uint256 effectiveAmount, bool isUSD) {
        uint256 nativeUSD = 0;
        bool hasEthFeed = false;
        if (nativeValue > 0) {
            (nativeUSD, hasEthFeed) = _getNativeUSD(hook, account, nativeValue);
        }

        uint256 tokenAmount = _extractTokenAmount(msgData);
        if (tokenAmount > 0) {
            (uint256 erc20USD, bool hasTokenFeed) = _extractERC20USD(hook, account, target, tokenAmount);
            if (hasTokenFeed) {
                return (nativeUSD + erc20USD, true);
            }
            if (TetherGuardHook(hook).getPriceFeed(account, NATIVE_ETH) != address(0)) {
                revert TetherGuardHook.MissingOraclePriceFeed(target);
            }
            return (nativeValue > 0 ? nativeValue : tokenAmount, false);
        }

        if (hasEthFeed) {
            return (nativeUSD, true);
        }

        return (nativeValue, false);
    }

    function getTotalPortfolioValueUSD(address account, address[] calldata tokens, address hook)
        external
        view
        returns (uint256 totalValueUSD, TetherGuardHook.TokenBalanceDetail[] memory details)
    {
        details = new TetherGuardHook.TokenBalanceDetail[](tokens.length);

        for (uint256 i = 0; i < tokens.length; i++) {
            address token = tokens[i];
            if (token == address(0) || token == NATIVE_ETH) {
                uint256 bal = account.balance;
                (uint256 price, uint8 feedDec) = _safeGetPrice(hook, account, NATIVE_ETH);
                uint256 val = _calculateUSD(bal, 18, price, feedDec);

                details[i] = TetherGuardHook.TokenBalanceDetail({
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

                (uint256 price, uint8 feedDec) = _safeGetPrice(hook, account, token);
                uint256 val = _calculateUSD(bal, dec, price, feedDec);

                details[i] = TetherGuardHook.TokenBalanceDetail({
                    token: token, symbol: sym, decimals: dec, balance: bal, priceUSD: price, valueUSD: val
                });
                totalValueUSD += val;
            }
        }
    }

    // --- Morning Review Storage and Dispatch ---

    function recordExecution(address account, address target, uint256 value) external returns (uint256 recId) {
        recId = ++executionCount[account];
        executionRecords[account][recId] = TetherGuardHook.AutonomousExecutionRecord({
            id: recId,
            target: target,
            value: value,
            timestamp: block.timestamp,
            status: TetherGuardHook.ReviewStatus.PENDING_REVIEW,
            userNote: ""
        });
    }

    function ratifyRecord(address account, uint256 recordId) external returns (uint256 value, uint256 timestamp) {
        TetherGuardHook.AutonomousExecutionRecord storage rec = executionRecords[account][recordId];
        if (rec.id == 0) revert TetherGuardHook.InvalidRecordId();
        if (rec.status != TetherGuardHook.ReviewStatus.PENDING_REVIEW) {
            revert TetherGuardHook.RecordAlreadyReviewed(rec.status);
        }
        rec.status = TetherGuardHook.ReviewStatus.LIKED_AND_RATIFIED;
        return (rec.value, rec.timestamp);
    }

    function flagRecordForRevert(address account, uint256 recordId, string calldata reason) external {
        TetherGuardHook.AutonomousExecutionRecord storage rec = executionRecords[account][recordId];
        if (rec.id == 0) revert TetherGuardHook.InvalidRecordId();
        if (rec.status != TetherGuardHook.ReviewStatus.PENDING_REVIEW) {
            revert TetherGuardHook.RecordAlreadyReviewed(rec.status);
        }
        rec.status = TetherGuardHook.ReviewStatus.REVERT_REQUESTED;
        rec.userNote = reason;
    }

    function submitRecordNote(address account, uint256 recordId, string calldata note) external {
        TetherGuardHook.AutonomousExecutionRecord storage rec = executionRecords[account][recordId];
        if (rec.id == 0) revert TetherGuardHook.InvalidRecordId();
        if (rec.status != TetherGuardHook.ReviewStatus.PENDING_REVIEW) {
            revert TetherGuardHook.RecordAlreadyReviewed(rec.status);
        }
        rec.status = TetherGuardHook.ReviewStatus.NOTED;
        rec.userNote = note;
    }

    function getExecutionRecord(address account, uint256 recordId)
        external
        view
        returns (TetherGuardHook.AutonomousExecutionRecord memory)
    {
        return executionRecords[account][recordId];
    }

    function getPendingReviews(
        address account,
        address /* hook */
    )
        external
        view
        returns (TetherGuardHook.AutonomousExecutionRecord[] memory pending)
    {
        uint256 total = executionCount[account];
        uint256 pendingCount = 0;
        for (uint256 i = 1; i <= total; i++) {
            if (executionRecords[account][i].status == TetherGuardHook.ReviewStatus.PENDING_REVIEW) {
                pendingCount++;
            }
        }

        pending = new TetherGuardHook.AutonomousExecutionRecord[](pendingCount);
        uint256 idx = 0;
        for (uint256 i = 1; i <= total; i++) {
            TetherGuardHook.AutonomousExecutionRecord memory rec = executionRecords[account][i];
            if (rec.status == TetherGuardHook.ReviewStatus.PENDING_REVIEW) {
                pending[idx] = rec;
                idx++;
            }
        }
    }

    // --- Cryptographic Signer Recovery Helpers ---

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

    function verifyCrossChainSpendSignature(
        TetherGuardHook.CrossChainSpendProof calldata proof,
        bytes calldata signature,
        uint256 chainId,
        address hook
    ) external pure returns (address) {
        bytes32 messageHash = keccak256(
            abi.encode(
                proof.account,
                proof.sourceChainId,
                proof.amountUSD,
                proof.epoch,
                proof.nonce,
                proof.deadline,
                chainId,
                hook
            )
        );
        bytes32 ethSignedMessageHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
        return _recoverSigner(ethSignedMessageHash, signature);
    }

    function verifySignApprovalSignature(
        address account,
        bytes32 executionHash,
        bool approve,
        uint256 nonce,
        uint256 deadline,
        uint256 chainId,
        address hook,
        bytes calldata signature
    ) external pure returns (address) {
        bytes32 messageHash = keccak256(abi.encode(account, executionHash, approve, nonce, deadline, chainId, hook));
        bytes32 ethSignedMessageHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
        return _recoverSigner(ethSignedMessageHash, signature);
    }

    // --- Deadman Switch & AI Heartbeat Storage ---
    uint256 public constant DEFAULT_DEADMAN_TIMEOUT = 90 days;
    uint256 public constant DEFAULT_AI_HEARTBEAT_TIMEOUT = 24 hours;

    mapping(address => uint256) public lastUserActivity;
    mapping(address => uint256) public lastAIHeartbeat;
    mapping(address => uint256) public customAIHeartbeatTimeout;
    mapping(address => address) public deadmanGuardians;
    mapping(address => uint256) public deadmanTimeouts;

    function _aiHeartbeatTimeout(address account) internal view returns (uint256) {
        uint256 hb = customAIHeartbeatTimeout[account];
        return hb > 0 ? hb : DEFAULT_AI_HEARTBEAT_TIMEOUT;
    }

    function _deadmanEligibleTime(address account) internal view returns (uint256) {
        uint256 timeout = deadmanTimeouts[account] > 0 ? deadmanTimeouts[account] : DEFAULT_DEADMAN_TIMEOUT;
        return lastUserActivity[account] + timeout;
    }

    function pingUserActivity(address account) external {
        lastUserActivity[account] = block.timestamp;
    }

    function recordAIHeartbeat(address account) external {
        lastAIHeartbeat[account] = block.timestamp;
    }

    function configureAIHeartbeatTimeout(address account, uint256 timeoutSeconds) external {
        require(timeoutSeconds >= 1 hours, "TIMEOUT_TOO_SHORT");
        customAIHeartbeatTimeout[account] = timeoutSeconds;
    }

    function configureDeadmanSwitch(address account, address guardian, uint256 timeoutSeconds) external {
        require(guardian != address(0), "INVALID_GUARDIAN");
        deadmanGuardians[account] = guardian;
        deadmanTimeouts[account] = timeoutSeconds > 0 ? timeoutSeconds : DEFAULT_DEADMAN_TIMEOUT;
        if (lastUserActivity[account] == 0) {
            lastUserActivity[account] = block.timestamp;
        }
    }

    function triggerDeadmanRecovery(address account, address caller, address newRootOwner) external returns (bool) {
        if (caller != deadmanGuardians[account]) {
            revert TetherGuardHook.UnauthorizedGuardian();
        }
        require(newRootOwner != address(0), "INVALID_NEW_OWNER");
        uint256 eligibleTime = _deadmanEligibleTime(account);
        if (lastUserActivity[account] == 0 || block.timestamp < eligibleTime) {
            revert TetherGuardHook.DeadmanSwitchNotEligible(lastUserActivity[account], eligibleTime);
        }
        lastUserActivity[account] = block.timestamp;
        return true;
    }

    function isAIHeartbeatAlive(address account) external view returns (bool) {
        if (lastAIHeartbeat[account] == 0) return true;
        return block.timestamp <= lastAIHeartbeat[account] + _aiHeartbeatTimeout(account);
    }

    function isDeadmanSwitchTriggerable(address account) external view returns (bool) {
        if (deadmanGuardians[account] == address(0) || lastUserActivity[account] == 0) return false;
        return block.timestamp >= _deadmanEligibleTime(account);
    }
}

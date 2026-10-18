// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {IERC20, IERC20Metadata} from "../interfaces/IERC20.sol";
import {AggregatorV3Interface} from "../interfaces/AggregatorV3Interface.sol";
import {TetherGuardHook} from "./TetherGuardHook.sol";

/**
 * @title PortfolioValuator
 * @author Tec-C Core Engineering Team
 * @notice Helper contract for multi-token portfolio valuation offloading TetherGuardHook runtime size.
 */
contract PortfolioValuator {
    address internal constant NATIVE_ETH = 0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE;

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

    function getPendingReviews(address account, address hook)
        external
        view
        returns (TetherGuardHook.AutonomousExecutionRecord[] memory pending)
    {
        uint256 total = TetherGuardHook(hook).executionCount(account);
        uint256 pendingCount = 0;
        for (uint256 i = 1; i <= total; i++) {
            if (
                TetherGuardHook(hook).getExecutionRecord(account, i).status
                    == TetherGuardHook.ReviewStatus.PENDING_REVIEW
            ) {
                pendingCount++;
            }
        }

        pending = new TetherGuardHook.AutonomousExecutionRecord[](pendingCount);
        uint256 idx = 0;
        for (uint256 i = 1; i <= total; i++) {
            TetherGuardHook.AutonomousExecutionRecord memory rec = TetherGuardHook(hook).getExecutionRecord(account, i);
            if (rec.status == TetherGuardHook.ReviewStatus.PENDING_REVIEW) {
                pending[idx] = rec;
                idx++;
            }
        }
    }
}

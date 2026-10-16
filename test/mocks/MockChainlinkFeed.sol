// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {AggregatorV3Interface} from "../../src/interfaces/AggregatorV3Interface.sol";

/**
 * @title MockChainlinkFeed
 * @notice Mock Chainlink Price Feed aggregator for unit testing.
 */
contract MockChainlinkFeed is AggregatorV3Interface {
    uint8 public override decimals;
    string public override description;
    uint256 public override version = 1;

    int256 public price;
    uint256 public updatedAt;

    constructor(uint8 _decimals, int256 _initialPrice, string memory _desc) {
        decimals = _decimals;
        price = _initialPrice;
        description = _desc;
        updatedAt = block.timestamp;
    }

    function setPrice(int256 _price) external {
        price = _price;
        updatedAt = block.timestamp;
    }

    function setUpdatedAt(uint256 _time) external {
        updatedAt = _time;
    }

    function latestRoundData()
        external
        view
        override
        returns (uint80 roundId, int256 answer, uint256 startedAt, uint256 _updatedAt, uint80 answeredInRound)
    {
        return (1, price, updatedAt, updatedAt, 1);
    }
}

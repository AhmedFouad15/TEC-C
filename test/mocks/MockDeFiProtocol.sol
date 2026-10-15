// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title MockDeFiProtocol
 * @dev Simulates Lido staking or Curve LP pools for Foundry unit testing.
 */
contract MockDeFiProtocol {
    uint256 public totalStaked;
    mapping(address => uint256) public balances;

    event Staked(address indexed user, uint256 amount);

    function stake() external payable {
        totalStaked += msg.value;
        balances[msg.sender] += msg.value;
        emit Staked(msg.sender, msg.value);
    }

    receive() external payable {
        totalStaked += msg.value;
        balances[msg.sender] += msg.value;
    }
}

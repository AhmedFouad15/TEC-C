// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import { Test, console } from "forge-std/Test.sol";
import { TecPaymaster } from "../src/paymaster/TecPaymaster.sol";
import { IPaymaster } from "../src/interfaces/IPaymaster.sol";
import { PackedUserOperation } from "../src/interfaces/PackedUserOperation.sol";

contract TecPaymasterTest is Test {
    TecPaymaster public paymaster;

    address public entryPoint = address(0xEEEE);
    address public tecAccount = address(0xBB22);
    address public sessionKey = address(0xCC33);

    function setUp() public {
        paymaster = new TecPaymaster(entryPoint);

        // Deposit 1 ETH into paymaster for tecAccount gas sponsorship
        vm.deal(tecAccount, 5 ether);
        vm.prank(tecAccount);
        paymaster.depositForAccount{value: 1 ether}(tecAccount);
    }

    function test_DepositAccounting() public view {
        assertEq(paymaster.accountBalances(tecAccount), 1 ether);
    }

    function test_LegitimateSponsorship_Succeeds() public {
        PackedUserOperation memory userOp;
        userOp.sender = tecAccount;
        userOp.signature = abi.encodePacked(sessionKey, hex"1234"); // 20 bytes sessionKey + dummy sig

        uint256 maxCost = 0.001 ether;

        (bytes memory context, uint256 validationData) = paymaster.validatePaymasterUserOp(
            userOp,
            bytes32(0),
            maxCost
        );

        assertEq(validationData, 0); // Sponsorship approved

        // Simulate EntryPoint postOp execution consuming 0.0008 ETH
        uint256 actualCost = 0.0008 ether;
        vm.prank(entryPoint);
        paymaster.postOp(
            IPaymaster.PostOpMode.opSucceeded,
            context,
            actualCost,
            1 gwei
        );

        assertEq(paymaster.accountBalances(tecAccount), 1 ether - actualCost);
        assertEq(paymaster.sponsoredGasPerSession(tecAccount, sessionKey), actualCost);
    }

    function test_GasGriefingLoop_HaltsAtMaxQuota() public {
        PackedUserOperation memory userOp;
        userOp.sender = tecAccount;
        userOp.signature = abi.encodePacked(sessionKey, hex"1234");

        // Simulate 5 successive operations consuming 0.001 ETH each
        for (uint256 i = 0; i < 5; i++) {
            (bytes memory context, uint256 validationData) = paymaster.validatePaymasterUserOp(
                userOp,
                bytes32(0),
                0.001 ether
            );
            assertEq(validationData, 0);

            vm.prank(entryPoint);
            paymaster.postOp(
                IPaymaster.PostOpMode.opSucceeded,
                context,
                0.001 ether,
                1 gwei
            );
        }

        // Now sessionKey has consumed 0.005 ETH (MAX_SESSION_GAS_BUDGET)
        assertEq(paymaster.sponsoredGasPerSession(tecAccount, sessionKey), paymaster.MAX_SESSION_GAS_BUDGET());

        // 6th operation attempted by AI Agent (griefing loop) -> Paymaster REJECTS sponsorship!
        (, uint256 rejectedValidationData) = paymaster.validatePaymasterUserOp(
            userOp,
            bytes32(0),
            0.0005 ether
        );

        assertEq(rejectedValidationData, 1); // Gas griefing halted!
    }

    function test_InsufficientDeposit_RejectsSponsorship() public view {
        address unfundedAccount = address(0x9999);
        PackedUserOperation memory userOp;
        userOp.sender = unfundedAccount;
        userOp.signature = abi.encodePacked(sessionKey, hex"1234");

        (, uint256 validationData) = paymaster.validatePaymasterUserOp(
            userOp,
            bytes32(0),
            0.01 ether
        );

        assertEq(validationData, 1); // Rejected
    }

    function test_WithdrawForAccount_Success() public {
        address payable refundee = payable(address(0x7777));
        uint256 initBalance = refundee.balance;

        // tecAccount withdraws 0.4 ETH of its 1 ETH deposit
        vm.prank(tecAccount);
        paymaster.withdrawForAccount(refundee, 0.4 ether);

        assertEq(paymaster.accountBalances(tecAccount), 0.6 ether);
        assertEq(refundee.balance, initBalance + 0.4 ether);
    }

    function test_WithdrawForAccount_InsufficientBalance_Reverts() public {
        address payable refundee = payable(address(0x7777));

        // Attempting to withdraw more than deposited (2 ETH > 1 ETH)
        vm.prank(tecAccount);
        vm.expectRevert(TecPaymaster.InsufficientAccountBalance.selector);
        paymaster.withdrawForAccount(refundee, 2 ether);
    }
}

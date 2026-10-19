// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import {PrivacyAuditAnchor} from "../src/audit/PrivacyAuditAnchor.sol";

contract PrivacyAuditAnchorTest is Test {
    PrivacyAuditAnchor internal anchor;
    address internal user = address(0xABCD);

    event AuditRecordAnchored(
        bytes32 indexed recordHash,
        address indexed account,
        PrivacyAuditAnchor.RecordType indexed recordType,
        uint256 timestamp
    );

    function setUp() public {
        anchor = new PrivacyAuditAnchor();
    }

    function test_AnchorRecord_Success() public {
        bytes32 recordHash = keccak256("account|USDC|DEPOSIT|1.000|1700000000|salt");
        vm.prank(user);

        vm.expectEmit(true, true, true, true);
        emit AuditRecordAnchored(recordHash, user, PrivacyAuditAnchor.RecordType.DEPEG_DETECTED, block.timestamp);

        bool ok = anchor.anchorRecord(recordHash, PrivacyAuditAnchor.RecordType.DEPEG_DETECTED);
        assertTrue(ok);

        (bool isAnchored, uint256 ts) = anchor.verifyRecord(recordHash);
        assertTrue(isAnchored);
        assertEq(ts, block.timestamp);

        assertEq(anchor.getAccountAnchorCount(user), 1);
        assertEq(anchor.getAccountAnchorAtIndex(user, 0), recordHash);
    }

    function test_AnchorRecord_ZeroHash_Reverts() public {
        vm.expectRevert("INVALID_HASH");
        anchor.anchorRecord(bytes32(0), PrivacyAuditAnchor.RecordType.MORNING_REVIEW_NOTE);
    }

    function test_AnchorRecord_DuplicateReplay_Reverts() public {
        bytes32 recordHash = keccak256("unique_tx_record");
        anchor.anchorRecord(recordHash, PrivacyAuditAnchor.RecordType.ARBITRAGE_EXECUTED);

        vm.expectRevert("ALREADY_ANCHORED");
        anchor.anchorRecord(recordHash, PrivacyAuditAnchor.RecordType.ARBITRAGE_EXECUTED);
    }
}

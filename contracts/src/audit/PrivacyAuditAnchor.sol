// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/**
 * @title PrivacyAuditAnchor
 * @notice Privacy-preserving cryptographic audit trail anchor for WeBank's FISCO BCOS consortium chain.
 * @dev Instead of dumping proprietary orderbook curves, client account balances, or trade details
 *      in plaintext on-chain, Tec-C commits cryptographic SHA-256 / Keccak commitments:
 *        RecordHash = SHA256(account || symbol || action || P_cons || timestamp || salt)
 *      Emits an immutable, timestamped event on the consortium chain, allowing regulatory verification
 *      (PBOC / CSRC / WeBank auditors) while strictly protecting commercial trade secrecy and client privacy.
 */
contract PrivacyAuditAnchor {
    enum RecordType {
        DEPEG_DETECTED, // 0: PegGuard de-peg regime detected & hedge calculated
        MORNING_REVIEW_NOTE, // 1: User Morning Review note / biometric ratification
        ARBITRAGE_EXECUTED // 2: Two-leg cross-market arbitrage execution commitment
    }

    event AuditRecordAnchored(
        bytes32 indexed recordHash, address indexed account, RecordType indexed recordType, uint256 timestamp
    );

    /// @notice recordHash => block.timestamp of commitment
    mapping(bytes32 => uint256) public anchoredAt;

    /// @notice account => array of record hashes anchored by this account
    mapping(address => bytes32[]) private _accountAnchors;

    /**
     * @notice Commits a cryptographic audit hash to the consortium chain.
     * @param recordHash The 32-byte cryptographic digest of the private event.
     * @param recordType The category of the anchored event.
     */
    function anchorRecord(bytes32 recordHash, RecordType recordType) external returns (bool) {
        require(recordHash != bytes32(0), "INVALID_HASH");
        require(anchoredAt[recordHash] == 0, "ALREADY_ANCHORED");

        anchoredAt[recordHash] = block.timestamp;
        _accountAnchors[msg.sender].push(recordHash);

        emit AuditRecordAnchored(recordHash, msg.sender, recordType, block.timestamp);
        return true;
    }

    /**
     * @notice Verifies if a given record hash has been anchored on-chain.
     * @param recordHash The 32-byte digest to verify.
     * @return isAnchored True if previously committed.
     * @return timestamp The block timestamp of commitment.
     */
    function verifyRecord(bytes32 recordHash) external view returns (bool isAnchored, uint256 timestamp) {
        timestamp = anchoredAt[recordHash];
        isAnchored = timestamp > 0;
    }

    /**
     * @notice Returns total number of audit records committed by an account.
     */
    function getAccountAnchorCount(address account) external view returns (uint256) {
        return _accountAnchors[account].length;
    }

    /**
     * @notice Returns the record hash at a specific index for an account.
     */
    function getAccountAnchorAtIndex(address account, uint256 index) external view returns (bytes32) {
        require(index < _accountAnchors[account].length, "INDEX_OUT_OF_BOUNDS");
        return _accountAnchors[account][index];
    }
}

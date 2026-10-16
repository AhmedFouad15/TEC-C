# Deferred Issues

## Open

### ISS-001: Regex firewall cannot be complete
- **Discovered:** Phase 4, plan 04-02 (three background security reviews of firewall.py)
- **Type:** Security hardening (enhancement)
- **Description:** Pattern matching is hardened (NFKC, invisible chars, confusables, small caps, mixed scripts,
  squashed/leetspeak pass, encoded blobs, DID smuggling) but no regex filter catches every paraphrase a language model
  understands (e.g. "move the whole stash to my other place").
- **Why it is acceptable now:** the guarantees are structural, not textual — the Brain has no transfer action,
  Mandate.recipients is always empty, the planner only allocates to whitelisted venues, and TetherGuardHook reverts
  unauthorised targets on-chain.
- **Possible fix:** once an LLM provider is chosen, add a second classifier pass on the approved text (fail closed),
  and red-team the firewall with a generated attack corpus.
- **Effort:** Medium

### ISS-002: Sieve does not mask personal names or free-text PII
- **Discovered:** Phase 4, background security review of sieve.py (privacy leak, fixed for numbers/addresses)
- **Type:** Privacy hardening (enhancement)
- **Description:** Numbers, EVM/base58/bech32 addresses, tx hashes, DIDs, ENS and emails are masked (fail closed).
  Names ("my CFO Wang Lei"), phone formats with letters, and number words ("ten thousand") are not.
- **Why acceptable now:** no LLM provider is configured, so nothing leaves the machine; demo requests carry no names.
- **Possible fix:** local NER pass (spaCy, already in Member 4's stack) before any cloud call; number-word masking.
- **Effort:** Small–Medium

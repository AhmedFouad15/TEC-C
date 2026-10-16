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

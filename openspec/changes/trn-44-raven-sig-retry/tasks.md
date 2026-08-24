## Tasks

- [ ] Update `crews/spec-ops/verify-admiral-sig`: add a bounded retry loop (3 attempts, 2s apart) around the secret file read before returning exit code 2; verify exit codes 0 and 1 behaviour is unchanged
- [ ] Update `academy/steering/STANDING_ORDERS.md`: expand the `verify-admiral-sig` bullet to document all three exit codes with the correct Raven response for each — 0 = act, 1 = treat as crew correspondence, 2 = transient hold (do not escalate, retry next check-in)
- [ ] Update `academy/orders/sdd.md`: add a note that exit code 2 from `verify-admiral-sig` is a transient race condition — Raven should hold the current cycle and not escalate to Admiral
- [ ] Add a test in `transport/test_transport.py` or a standalone test script: verify that `verify-admiral-sig` exits 0 when the secret matches, exits 1 when it mismatches, and exits 2 (after retries) when the file is absent — use subprocess with a temp file to avoid modifying real crew state

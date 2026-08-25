## 1. Code change

- [x] 1.1 In `_ensure_crew_running` (transport/server.py), locate the leader path's restart sequence and remove the first `_wait_gateway` call — the one that occurs between `container_start` and `_patch_crew_config`. The `container_start` → `_patch_crew_config` → `container_stop` → `container_start` → `_wait_gateway` sequence should remain, just without the wait between the first start and the patch.
- [x] 1.2 Update the WORKAROUND comment to accurately describe the new sequence: start (no wait), exec-patch, stop, start, wait.
- [x] 1.3 Ensure the provisional exec patch can create its config destination before gateway readiness.

## 2. Tests

- [x] 2.1 Add or update a unit test asserting that `container_start` is called exactly twice and `_wait_gateway` is called exactly once per wake cycle in the normal restart path (i.e., no gateway-dead-inside-running-container branch).
- [x] 2.2 Verify the existing restart tests still pass — confirm no test was asserting the old double-wait behaviour.

## 3. Verification

- [x] 3.1 Run `bash tests/run.sh --unit` and confirm all 329+ tests pass.
- [x] 3.2 Manual deployment verification — skipped (no sandbox access to a target host); the automated unit suite in 3.1 is the verification for this change.

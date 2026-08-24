## 1. Code change

- [ ] 1.1 In `_ensure_crew_running` (transport/server.py), locate the leader path's restart sequence and remove the first `_wait_gateway` call — the one that occurs between `container_start` and `_patch_crew_config`. The `container_start` → `_patch_crew_config` → `container_stop` → `container_start` → `_wait_gateway` sequence should remain, just without the wait between the first start and the patch.
- [ ] 1.2 Update the WORKAROUND comment to accurately describe the new sequence: start (no wait), exec-patch, stop, start, wait.

## 2. Tests

- [ ] 2.1 Add or update a unit test asserting that `container_start` is called exactly twice and `_wait_gateway` is called exactly once per wake cycle in the normal restart path (i.e., no gateway-dead-inside-running-container branch).
- [ ] 2.2 Verify the existing restart tests still pass — confirm no test was asserting the old double-wait behaviour.

## 3. Verification

- [ ] 3.1 Run `bash tests/run.sh --unit` and confirm all 329+ tests pass.
- [ ] 3.2 Deploy to a target host and manually verify a crew wake (idle an existing crew, then dispatch a task and time the response).

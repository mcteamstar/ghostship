# Tasks: crew-lifecycle-resilience

See `design.md` for approach rationale; `proposal.md` for scope and motivation.
Each group below is independently mergeable — the only strict ordering is that
the test tasks (group 6) depend on the implementation groups they cover.

## 1. Recovery Self-Deadlock (Critical — D1)

- [x] 1.1 In `transport/lifecycle.py` `_enroll_crew_members`, replace the `_crew_api_with_recovery` call with a direct `_crew_api` call wrapped in try/except; log and continue on failure (non-fatal semantics unchanged)
- [x] 1.2 Add a unit test that acquires the per-crew recovery lock, then calls `_enroll_crew_members` from within it on a stubbed crew, and asserts the call completes without blocking (no lock re-entry deadlock)
- [x] 1.3 Verify the two call sites (`lifecycle.py:851` launch path and `:1651` restart-recovery path) both use the updated `_enroll_crew_members`

## 2. Registry I/O Error Handling (High — D2)

- [x] 2.1 In `transport/registry.py` `_load_registry`, replace the bare `except Exception` clause (which returns `{"crews": {}}`) with `raise`, so I/O errors propagate to the caller
- [x] 2.2 Audit all call sites of `_load_registry` in `lifecycle.py`, `monitors.py`, and `server.py`; add an explicit except clause at each background-thread call site that logs and continues (fail-open, matching existing behaviour)
- [x] 2.3 In `server.py` around line 2428, ensure the code path that calls `_load_registry` then immediately calls `_save_registry` skips the save when `_load_registry` raises
- [x] 2.4 Add a unit test: mock `REGISTRY_PATH.read_text` to raise `PermissionError`; assert `_load_registry` raises rather than returning `{"crews": {}}` and that the registry file is not overwritten

## 3. Idle Reaper TOCTOU (Medium — D3)

- [x] 3.1 In `transport/monitors.py` `_idle_monitor`, after completing all HTTP activity checks for a candidate crew, re-acquire `_registry_lock` and re-read `last_used` from the live registry before stopping; skip the stop if `last_used` is now within `GA_IDLE_TIMEOUT_SECS`
- [x] 3.2 Perform the actual `container_stop` call while the lock from 3.1 is still held (or using a brief re-acquire immediately before the stop), so the re-check and the stop are atomic with respect to `_touch_crew`
- [x] 3.3 Add a unit test: simulate a crew touched (last_used updated) during the HTTP-check window; assert the reaper skips the stop after the re-check

## 4. Podman Error Semantics (High — D4)

- [x] 4.1 In `transport/podman.py`, update `container_exists` to return `False` only on 404 and raise a new `PodmanError` (or re-raise `httpx.HTTPStatusError`) on other non-200 responses
- [x] 4.2 In `transport/podman.py`, update `container_is_running` to return `False` only on 404 or non-running state; raise on other non-200 responses
- [x] 4.3 Audit all callers of `container_exists` and `container_is_running` in `lifecycle.py` (lines 605, 1425, and active-limit check in `_ensure_crew_running`) and `monitors.py`; update each to catch the new exception and handle it explicitly (log-and-skip or fail-open as appropriate)
- [x] 4.4 In `lifecycle.py`, on the active-limit correction path, skip the registry "running→stopped" correction for a crew whose Podman check raised rather than returned `False` (do not remove a crew from running count on an ambiguous error)
- [x] 4.5 Add unit tests for `container_exists` and `container_is_running`: 404 → False, 500 → raises, 200+running → True, 200+stopped → False

## 5. Restart Race and Retry / Leak Cleanup (High / Medium — D5, D6, D7)

- [x] 5.1 In `transport/lifecycle.py` `_ensure_crew_running`, move the `crew_id in _startup_events` check to before the `container_is_running` probe and the `container_stop` call (D5: restart race guard)
- [x] 5.2 In `_phase0_transient_503` and `_phase1_stale_cookie`, skip the retry when `method` is not in `{GET, HEAD, PUT}`; raise the last exception instead (D6: idempotent-only retry)
- [x] 5.3 In `lifecycle.py` launch failure path (around line 1984), add a finally block that calls `_nuke_login_container` when a login container was created before the failure (D7a: login container leak)
- [x] 5.4 In `lifecycle.py` `_ensure_crew_running`, on the registry-write failure path (around line 765), stop the container before returning the error so the container state matches the registry entry (D7b: container/registry state mismatch)
- [x] 5.5 In `server.py` launch failure path (around line 2592), add cleanup of the admiral secret file to the existing failure cleanup block or a finally clause (D7c: admiral secret file leak)
- [x] 5.6 Add a unit test for D5: assert that a second concurrent call to `_ensure_crew_running` for the same crew takes the waiter path even if `container_is_running` would return True (by verifying the startup-event check fires first)
- [x] 5.7 Add a unit test for D6: assert that `_phase0_transient_503` and `_phase1_stale_cookie` do not retry a POST request on connection reset
      <!-- NOTE: a connection reset routes to _phase2_dead_gateway, which is where the
           idempotency guard (D6) actually lives and where it belongs: a 503 (phase-0, still
           spawning) and a 400/401/403 (phase-1, auth reject) mean the request was NOT acted
           upon, so retrying is safe for any method; only a connection reset mid-flight can
           have had a side effect. The test (IdempotentRetryTests) asserts POST is not
           retried on reset and GET is, through _crew_api_with_recovery. -->


## 6. Integration and Regression

- [x] 6.1 Write a lock-re-entry regression test for the deadlock (D1): confirms `_crew_api_with_recovery` can be called while the recovery lock is held, without hanging
- [x] 6.2 Write a registry-durability integration test (D2): confirm that a transport restart after a `PermissionError` during registry read does not produce an empty registry on next write
- [x] 6.3 Update or add inline comments on `_crew_api_with_recovery` to document the non-reentrant contract (so future callers of `_enroll_crew_members` do not reintroduce the pattern)
- [x] 6.4 Run the full transport unit test suite; confirm no regressions

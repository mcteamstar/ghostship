## 1. Test infrastructure and mocks

- [x] 1.1 Create `ReconcilePodman` mock class with configurable container_exists/container_is_running/container_start responses and call recording
- [x] 1.2 Create `IdleMonitorPodman` mock class with container_is_running/container_stop recording
- [x] 1.3 Create helper to write/read a temporary registry JSON file for test isolation
- [x] 1.4 Create mock HTTP response factory for `/api/spawn` and `/api/crons` responses used by `_idle_monitor`

## 2. _reconcile_registry tests

- [x] 2.1 Test: orphaned `ga-login-*` container is swept on startup
- [x] 2.2 Test: gone crew (container doesn't exist) is removed from registry
- [x] 2.3 Test: stopped crew is restarted, cookie refreshed, registry updated to "running"
- [x] 2.4 Test: stopped crew whose gateway fails to start is marked "stopped" (not removed)
- [x] 2.5 Test: running crew is left unchanged
- [x] 2.6 Test: stale "launching" entry with missing container is removed

## 3. _reconcile_registry stale-snapshot fix

- [x] 3.1 Add `if cid in reg["crews"]` guard before applying updates in the write-back section of `_reconcile_registry`
- [x] 3.2 Test: crew removed by another thread between snapshot and write-back is NOT resurrected

## 4. _idle_monitor tests

- [x] 4.1 Test: crew with active dispatch task (done=false) is not stopped, last_used updated
- [x] 4.2 Test: crew with enabled cron job is not stopped, last_used updated
- [x] 4.3 Test: genuinely idle crew is stopped, registry marked "stopped"
- [x] 4.4 Test: recently used crew (within timeout) is skipped
- [x] 4.5 Test: already-stopped container is skipped (no double-stop)

## 5. _idle_monitor 401 cookie refresh fix

- [x] 5.1 Modify `_idle_monitor` to catch 401 from `/api/spawn` and `/api/crons`, attempt `_mint_cookie`, retry on success, skip crew on failure
- [x] 5.2 Test: 401 response triggers cookie refresh and successful retry
- [x] 5.3 Test: 401 with failed cookie refresh skips crew (does not stop it)

## 6. _finish_crew_setup ordering tests

- [x] 6.1 Test: full happy-path setup records steps in exact required order (gateway wait → auth inject → config patch → restart → copies → openspec seed → wait agent files → model patch → cookie mint → registry write)
- [x] 6.2 Test: gateway failure after auth restart triggers cleanup and returns error without executing later steps

## 7. Login flow edge case tests

- [x] 7.1 Test: PTY exec with no URL within 15s returns 500 and cleans up container
- [x] 7.2 Test: Region prompt is answered with KIRO_REGION when encountered after Start URL
- [x] 7.3 Test: concurrent POST /login while _login_pending is set returns 409

## 8. _handle_login_get guard-clear fix

- [x] 8.1 Verify existing code clears `_login_pending` after `_nuke_login_container` (confirm no reorder needed)
- [x] 8.2 Test: concurrent POST /login during the cleanup window (between auth detection and guard clear) receives 409

## 9. Validation

- [x] 9.1 Run full test suite: `python -m pytest transport/test_transport.py -v`
- [x] 9.2 Run `openspec validate --changes --store repo` to confirm planning completeness

## 10. Test suite portability

- [x] 10.1 Identify all test classes/methods that call real `podman` commands or depend on a live Podman socket
- [x] 10.2 Decorate each Podman-dependent class/method with `@unittest.skipUnless(shutil.which("podman"), "requires podman")`
- [x] 10.3 Add a comment block at the top of `test_transport.py` listing Podman-dependent vs portable test classes, and confirm the portable subset runs to completion inside a crew container

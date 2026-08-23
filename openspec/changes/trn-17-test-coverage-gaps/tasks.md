## 1. Test infrastructure and mocks

- [ ] 1.1 Create `ReconcilePodman` mock class with configurable container_exists/container_is_running/container_start responses and call recording
- [ ] 1.2 Create `IdleMonitorPodman` mock class with container_is_running/container_stop recording
- [ ] 1.3 Create helper to write/read a temporary registry JSON file for test isolation
- [ ] 1.4 Create mock HTTP response factory for `/api/spawn` and `/api/crons` responses used by `_idle_monitor`

## 2. _reconcile_registry tests

- [ ] 2.1 Test: orphaned `ga-login-*` container is swept on startup
- [ ] 2.2 Test: gone crew (container doesn't exist) is removed from registry
- [ ] 2.3 Test: stopped crew is restarted, cookie refreshed, registry updated to "running"
- [ ] 2.4 Test: stopped crew whose gateway fails to start is marked "stopped" (not removed)
- [ ] 2.5 Test: running crew is left unchanged
- [ ] 2.6 Test: stale "launching" entry with missing container is removed

## 3. _reconcile_registry stale-snapshot fix

- [ ] 3.1 Add `if cid in reg["crews"]` guard before applying updates in the write-back section of `_reconcile_registry`
- [ ] 3.2 Test: crew removed by another thread between snapshot and write-back is NOT resurrected

## 4. _idle_monitor tests

- [ ] 4.1 Test: crew with active dispatch task (done=false) is not stopped, last_used updated
- [ ] 4.2 Test: crew with enabled cron job is not stopped, last_used updated
- [ ] 4.3 Test: genuinely idle crew is stopped, registry marked "stopped"
- [ ] 4.4 Test: recently used crew (within timeout) is skipped
- [ ] 4.5 Test: already-stopped container is skipped (no double-stop)

## 5. _idle_monitor 401 cookie refresh fix

- [ ] 5.1 Modify `_idle_monitor` to catch 401 from `/api/spawn` and `/api/crons`, attempt `_mint_cookie`, retry on success, skip crew on failure
- [ ] 5.2 Test: 401 response triggers cookie refresh and successful retry
- [ ] 5.3 Test: 401 with failed cookie refresh skips crew (does not stop it)

## 6. _finish_crew_setup ordering tests

- [ ] 6.1 Test: full happy-path setup records steps in exact required order (gateway wait → auth inject → config patch → restart → copies → openspec seed → wait agent files → model patch → cookie mint → registry write)
- [ ] 6.2 Test: gateway failure after auth restart triggers cleanup and returns error without executing later steps

## 7. Login flow edge case tests

- [ ] 7.1 Test: PTY exec with no URL within 15s returns 500 and cleans up container
- [ ] 7.2 Test: Region prompt is answered with KIRO_REGION when encountered after Start URL
- [ ] 7.3 Test: concurrent POST /login while _login_pending is set returns 409

## 8. _handle_login_get guard-clear fix

- [ ] 8.1 Verify existing code clears `_login_pending` after `_nuke_login_container` (confirm no reorder needed)
- [ ] 8.2 Test: concurrent POST /login during the cleanup window (between auth detection and guard clear) receives 409

## 9. Validation

- [ ] 9.1 Run full test suite: `python -m pytest transport/test_transport.py -v`
- [ ] 9.2 Run `openspec validate --changes --store repo` to confirm planning completeness

## 10. Test suite portability

- [ ] 10.1 Identify all test classes/methods that call real `podman` commands or depend on a live Podman socket
- [ ] 10.2 Decorate each Podman-dependent class/method with `@unittest.skipUnless(shutil.which("podman"), "requires podman")`
- [ ] 10.3 Add a comment block at the top of `test_transport.py` listing Podman-dependent vs portable test classes, and confirm the portable subset runs to completion inside a crew container

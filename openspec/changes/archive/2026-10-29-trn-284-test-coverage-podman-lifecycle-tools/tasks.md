## 1. test_podman.py — new file

- [x] 1.1 Check whether `respx` is available in the test venv
  (`python -c "import respx"`). If not, use `unittest.mock.patch` on
  `httpx.Client.send` instead.
- [x] 1.2 Create `tests/unit/test_podman.py`. Add tests for:
  - `container_create` — success (201) and error (500)
  - `container_exec_stdin` — success and non-zero exit code
  - `container_archive_put` / `container_archive_get` — success
  - `network_create` / `network_connect` / `network_disconnect` — success
  - `volume_create` / `volume_remove` — success
  - Socket failure (connection refused) raises a structured exception
- [x] 1.3 Add a FakePodmanClient interface parity test: iterate all public methods of
  `PodmanClient` and assert each exists on `FakePodmanClient` with a compatible
  signature using `inspect.signature`.

## 2. test_tools.py — new file

- [x] 2.1 Create `tests/unit/test_tools.py`. Read `transport/tools.py` to understand
  the module-level `registry` and `_get_podman` patterns used.
- [x] 2.2 Add tests for `nuke()`:
  - `confirm=False` returns preview, no container op
  - `confirm=True` calls `container_stop` and `container_remove`
- [x] 2.3 Add tests for `schedule()`:
  - Missing `name` returns error
  - Invalid `interval` (< 60) returns error
  - `action="cancel"` on non-existent job returns structured error
- [x] 2.4 Add tests for `dispatch()` error paths:
  - Crew not found returns `{"error": ...}`
  - Gateway unreachable returns `{"error": ...}`
- [x] 2.5 Add tests for `resource_agents` and `resource_jobs` MCP resource handlers:
  - Returns correct shape with empty and non-empty registry
- [x] 2.6 Add tests for `supply` / `evac` stopped-crew branches.

## 3. test_lifecycle.py extensions

- [x] 3.1 Add tests for `_reconcile_registry`:
  - Stale running entry (container stopped) gets corrected to `stopped`
  - Entry with recent activity is preserved
- [x] 3.2 Add tests for `_reseed_crew_schedules`:
  - Captain schedule in registry is re-registered after simulated restart
  - Missing schedule entry is skipped without error
- [x] 3.3 Add tests for `_mint_cookie` / `_refresh_cookie`:
  - `_mint_cookie` returns a non-empty token and stores it in the registry
  - `_refresh_cookie` updates the in-memory entry atomically (regression for H-1 fix)

## 4. test_captain_engine.py extensions

- [x] 4.1 Add test for `_dispatch_captain_checkin` with memory pressure:
  - Patch `_get_host_memory_gb_cached` to return below threshold
  - Assert no spawn call is made
  - Assert `immediate_dispatch_error` starts with `memory_pressure:`
- [x] 4.2 Add test for `_dispatch_captain_checkin` with claude backend model override:
  - Crew has `acp_backend="claude"` and a configured default model
  - Assert spawn request uses crew model, not raven.json model
- [x] 4.3 Add test for `_steer_captain_checkin` 400-on-continue fallback:
  - Mock `_crew_api` to raise `httpx.HTTPStatusError` with status 400 on `/continue`
  - Assert steer (interrupt) is attempted instead
- [x] 4.4 Add test for `_captain_do_order` re-order of existing schedule:
  - Call `_captain_do_order` when a captain entry already exists
  - Assert the existing entry is updated, not duplicated

## 5. test_server.py, test_files.py, test_academy.py targeted additions

- [x] 5.1 `test_server.py`: Add test for crew API proxy handler returning 404 on
  unknown crew.
- [x] 5.2 `test_files.py`: Add test for upload path-traversal rejection in
  `_safe_workspace_path` (e.g. `../../etc/passwd` resolves outside workspace root).
- [x] 5.3 `test_academy.py`: Add test for `_load_composition_registry` with missing
  file (returns default compositions) and malformed JSON (logs error, returns default).

## 6. Verification

- [x] 6.1 Run `bash scripts/run.sh --unit` — all tests pass.
- [x] 6.2 Confirm new test file count: `ls tests/unit/test_*.py | wc -l` should be
  36 (adding test_podman.py and test_tools.py to the pre-TRN-284 baseline of 34;
  the original estimate of 35 was off by one — there were 34 test files, not 35).

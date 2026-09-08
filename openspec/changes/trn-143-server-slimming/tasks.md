## 1. Proxy boilerplate helper

- [ ] 1.1 Add `async def _resolve_crew_for_proxy(path: str)` to `server.py` — returns `(crew_id, sub_path, crew_dict)` on success or a `Response` on failure (404 parse error, 404 unknown crew, 502 ensure-running failure)
- [ ] 1.2 Replace the repeated preamble in `_handle_crew_ui_proxy` (line ~1207–1222) with a call to `_resolve_crew_for_proxy`
- [ ] 1.3 Replace the repeated preamble in `_handle_crew_api_proxy` (line ~1438–1453) with a call to `_resolve_crew_for_proxy`
- [ ] 1.4 Replace the repeated preamble in `_handle_crew_ui_ws_proxy` (line ~1326–1339) with a call to `_resolve_crew_for_proxy`
- [ ] 1.5 Replace the repeated preamble in `_handle_crew_dashboard_post` with the parse+require portion of `_resolve_crew_for_proxy` (no auto-wake needed for dashboard handlers)
- [ ] 1.6 Run test suite; verify all proxy handler tests pass

## 2. Move pickup and dispatch helpers to lifecycle.py

- [ ] 2.1 Move `_pickup_single` from `server.py` to `lifecycle.py` (place next to `_pickup_batch`)
- [ ] 2.2 Move `_pickup_list` from `server.py` to `lifecycle.py`
- [ ] 2.3 Move `_dispatch_batch` from `server.py` to `lifecycle.py`
- [ ] 2.4 Move `_record_last_task_at` from `server.py` to `lifecycle.py`
- [ ] 2.5 Update `server.py` — import `_pickup_single`, `_pickup_list`, `_dispatch_batch`, `_record_last_task_at` from `lifecycle`; the `pickup` and `dispatch` MCP tools remain in `server.py` as callers
- [ ] 2.6 Audit `tests/unit/test_server.py` and `test_lifecycle.py` — update any `patch('transport.server._pickup_single', ...)` or similar to patch the new owning module `transport.lifecycle`
- [ ] 2.7 Run test suite; verify all pickup and dispatch tests pass

## 3. Move login machinery to lifecycle.py

- [ ] 3.1 Move `_auth_file_path`, `_read_auth_file`, `_write_auth_file` from `server.py` to `lifecycle.py`
- [ ] 3.2 Move `_login_pending` and `_login_pending_lock` module-level globals from `server.py` to `lifecycle.py`
- [ ] 3.3 Move `_initiate_login` from `server.py` to `lifecycle.py` — verify no `server.*` imports are introduced into `lifecycle.py`
- [ ] 3.4 Update `server.py` — import the moved functions/globals from `lifecycle`; keep `_handle_login_post`, `_handle_login_get`, `_handle_logout_post` in `server.py` as thin HTTP handlers
- [ ] 3.5 Audit tests that patch `server._login_pending`, `server._initiate_login`, `server._read_auth_file`, etc. — update to patch `lifecycle.*`
- [ ] 3.6 Run test suite; verify all login flow tests pass

## 4. Consolidate test FakeHTTP / FakeResponse mocks

- [ ] 4.1 Audit the four independent `FakeHTTP`/`FakeResponse` definitions in `test_file_transfer.py`, `test_recovery.py`, `test_monitors.py`, `test_server.py` — note any constructor signature differences
- [ ] 4.2 Add consolidated `FakeHTTP` and `FakeResponse` classes to `tests/unit/helpers.py` with a unified interface covering all usage patterns
- [ ] 4.3 Update `test_recovery.py` to import from `helpers` and remove its local definitions
- [ ] 4.4 Update `test_monitors.py` to import from `helpers` and remove its local definitions
- [ ] 4.5 Update `test_server.py` inline class definitions (lines ~2507, ~2541, ~2574) to use `helpers.FakeHTTP` / `helpers.FakeResponse`
- [ ] 4.6 Run test suite; verify all affected tests pass

## 5. Final verification and commit

- [ ] 5.1 Run the full unit test suite (`python3 -m unittest discover -s tests/unit -p "test_*.py" -t .`) — confirm 804 tests pass, 0 new errors
- [ ] 5.2 Verify `lifecycle.py` does not import from `server.py` (grep check)
- [ ] 5.3 Commit: `refactor: slim server.py — move misplaced functions to lifecycle`

# Tasks

## 1. Fix _crew_api_with_recovery

- [x] 1.1 In `transport/lifecycle.py` `_crew_api_with_recovery`, add the `/continue` path guard immediately before the `_phase1_stale_cookie` call: re-raise `HTTPStatusError` when `status == 400` and `"/continue" in path`. Verify: `bash -n transport/lifecycle.py` passes; read the change to confirm 400 on non-/continue paths still reaches phase-1.

## 2. Fix _steer_captain_checkin

- [x] 2.1 In `transport/server.py` `_steer_captain_checkin`, extend the conversation-gone fallback condition to include `"400 Bad Request" in err_str and "/continue" in err_str` (both checks together to avoid false positives on unrelated 400s). Add a log message identifying the 400 path. Verify: module imports cleanly.
- [x] 2.2 Before calling `_dispatch_captain_checkin` in the fallback, add a registry update that sets `current_task_id = None` for the crew's captain schedule entry. Verify: test 3.1 asserts current_task_id is cleared.

## 3. Tests

- [x] 3.1 In `tests/unit/test_captain.py` (or `test_monitors.py`), add a test: mock `_crew_api_with_recovery` to raise `httpx.HTTPStatusError` with status 400 and URL containing `/continue`; call `_steer_captain_checkin`; assert it calls `_dispatch_captain_checkin` (not re-raises) and clears `current_task_id` in the registry. Verify: `tests/run.sh --unit` passes.
- [x] 3.2 Add a test: mock `_crew_api_with_recovery` to raise `httpx.HTTPStatusError` with status 400 on a non-/continue path (e.g. `/api/spawn`); assert it still propagates (not swallowed by the /continue guard). Verify: test passes.
- [x] 3.3 Add a test confirming the existing 404/conversation_gone path still works after the change. Verify: test passes.

## Workflow follow-up

- Archive the change after tests pass and the PR is merged.
- Update the TRN-230 Plane ticket to Done.

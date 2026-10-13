# Tasks

## 1. QA-1 — Release registry lock before container_stop

- [x] 1.1 In `transport/monitors.py` `_idle_monitor` (~L551–575), add a `_stopping` in-flight flag to the registry entry inside the lock, then release the lock before calling `podman.container_stop`. After `container_stop` returns, re-acquire the lock to write back `status: stopped` and clear the flag. Verify: the lock is not held during `container_stop` by inspecting the code path; add a unit test that confirms a concurrent registry read can proceed while a simulated `container_stop` is in progress.
- [x] 1.2 Add a unit test for double-stop prevention: mock two concurrent idle monitor ticks targeting the same crew; verify `container_stop` is called exactly once. Run `tests/run.sh --unit` and confirm pass.

## 2. QA-2 — Registry existence check after container_start

- [x] 2.1 In `transport/lifecycle.py` `_ensure_crew_running`, add a registry existence check immediately after `container_start` returns and before the dashboard cookie write and member enrollment. If `crew_id` is no longer in `_registry`, log at INFO level and return a sentinel value indicating nuke-during-restart. Verify: a unit test confirms the check triggers when a mock nuke removes the registry entry mid-restart.
- [x] 2.2 Add a unit test: mock `_ensure_crew_running` where `nuke()` removes the registry entry between `container_start` and post-start setup; verify no error is raised and the INFO log is emitted. Run `tests/run.sh --unit` and confirm pass.

## 3. QA-3 — Harden /continue path detection

- [x] 3.1 In `transport/lifecycle.py` `_crew_api_with_recovery`, change the `/continue` detection from `'continue' in path` to `path.endswith('/continue')`. Verify: existing unit tests for the `_crew_api_with_recovery` continue-path handling still pass; add a test case confirming a path like `/api/continue-session/abc` does NOT trigger the continue-path bypass. Run `tests/run.sh --unit` and confirm pass.

## 4. Integration check

- [x] 4.1 Run `tests/run.sh --unit` to confirm all three fixes pass together with no regressions.

## Workflow follow-up

- Archive the change after review.

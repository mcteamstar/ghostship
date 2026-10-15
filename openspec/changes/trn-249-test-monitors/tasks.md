# Tasks

## 1. Pure helper tests — _cron_activity_since and _cron_has_enabled_job

- [x] 1.1 In `tests/unit/test_monitors.py`, create a `TestCronActivityHelpers` class. Add tests for `_cron_activity_since` covering: `is_running=True` → returns `True`; job with `running_since` newer than `last_used` → returns `True`; job with `last_run_ts` newer than `last_used` → returns `True`; all timestamps older than `last_used` and not running → returns `False`; empty jobs list → returns `False`; non-dict payload → returns `False`. Verify: `tests/run.sh --unit` passes.

- [x] 1.2 Add a `TestCronHasEnabledJob` class in the same file. Cover: at least one job with `enabled: True` → returns `True`; all jobs `enabled: False` or missing → returns `False`; empty list → returns `False`; non-dict payload → returns `False`. Verify: `tests/run.sh --unit` passes.

## 2. _note_idle_skip deduplication tests

- [x] 2.1 Add a `TestNoteIdleSkip` class in `tests/unit/test_monitors.py`. Clear `monitors._idle_skip_reasons` in `setUp` and `tearDown` to isolate state. Cover: first call for a crew → logs at INFO; second call with same reason → no second log; second call with different reason → new log emitted. Use `self.assertLogs("transport.lifecycle", level="INFO")` as context manager. Verify: `tests/run.sh --unit` passes.

## 3. _schedule_monitor iteration tests

- [x] 3.1 Add a `TestScheduleMonitorIteration` class in `tests/unit/test_monitors.py`. In `setUp`, call `monitors.bind_lifecycle(...)` with stub callables. Pre-populate `registry._reg["crews"]` with synthetic crew state. Patch `time.sleep` to no-op. Cover: due job with gateway-enabled state → `_crew_api_with_recovery` called with POST `/api/spawn` and `next_fire_at` advanced. Verify: `tests/run.sh --unit` passes.

- [x] 3.2 Add schedule monitor tests for skip paths: not-yet-due job (`next_fire_at > now`) → `_crew_api_with_recovery` not called; `enabled: False` job → skipped; `type == "captain"` job → skipped. Verify: `tests/run.sh --unit` passes.

- [x] 3.3 Add schedule monitor tests for failure and gateway-sync paths: `_ensure_crew_running` raises → `next_fire_at` advanced, no spawn call; gateway `/api/crons` returns job with `enabled: false` → registry entry set to disabled, no spawn call; gateway fetch raises → fail-open (spawn proceeds). Verify: `tests/run.sh --unit` passes.

- [x] 3.4 Add schedule monitor test for one-shot job teardown: `one_shot: True` job fires successfully → registry entry has `enabled: False` and `next_fire_at` set to `_NEVER_FIRE_AT`, and `_crew_api_with_recovery` called with DELETE `/api/crons/<job_id>`. Verify: `tests/run.sh --unit` passes.

## 4. _idle_monitor iteration tests — container status and task checks

- [x] 4.1 Add a `TestIdleMonitorIteration` class in `tests/unit/test_monitors.py`. In `setUp`, call `monitors.bind_lifecycle(...)` with stubs; install a `FakePodmanClient` via `patch.object(monitors, "_get_podman", ...)`. Patch `monitors._http` with a fake HTTP module. Pre-populate `registry._reg["crews"]` with a running crew entry past the idle timeout. Cover: crew with active task (`done: false` in `/api/spawn`) → `container_stop` not called, `_touch_crew` called. Verify: `tests/run.sh --unit` passes.

- [x] 4.2 Add idle monitor tests for cron-hold paths: `/api/crons` returns a job with `enabled: True` → `container_stop` not called; job with `last_run_ts` more recent than `last_used` → `container_stop` not called; no active tasks and no cron jobs → `container_stop` called and `registry._reg["crews"][crew_id]["status"]` set to `"stopped"`. Verify: `tests/run.sh --unit` passes.

- [x] 4.3 Add idle monitor tests for skip conditions: container not running → `container_stop` not called; `status == "auth_required"` → skipped entirely; `last_used` within `GA_IDLE_TIMEOUT_SECS` → not stopped. Verify: `tests/run.sh --unit` passes.

- [x] 4.4 Add idle monitor tests for cookie-refresh branch: `/api/spawn` returns 401 AND `_mint_cookie` returns a new value → request retried with new cookie; `/api/spawn` returns 401 AND `_mint_cookie` returns `None` → fail-open skip (no stop). Same two cases for `/api/crons`. Verify: `tests/run.sh --unit` passes.

- [x] 4.5 Add idle monitor tests for captain-schedule hold: registry entry has a captain-type schedule with `enabled: True` and `next_fire_at < _NEVER_FIRE_AT` → `container_stop` not called and `_touch_crew` called. Verify: `tests/run.sh --unit` passes.

- [x] 4.6 Add idle monitor tests for TOCTOU guard and `_stopping` flag: simulate `_touch_crew` updating `last_used` between checks (set `registry._reg["crews"][crew_id]["last_used"]` to `now` inside the lock callback) → `container_stop` not called; pre-set `registry._reg["crews"][crew_id]["_stopping"] = True` → `container_stop` not called. Verify: `tests/run.sh --unit` passes.

- [x] 4.7 Add idle monitor tests for `_stopping` flag lifecycle: after successful `container_stop` → `_stopping` removed from registry and `status == "stopped"`; if `container_stop` raises → `_stopping` cleared and `status` NOT changed to `"stopped"`. Verify: `tests/run.sh --unit` passes.

## 5. _captain_monitor iteration tests

- [x] 5.1 Add a `TestCaptainMonitorIteration` class in `tests/unit/test_monitors.py`. In `setUp`, call `monitors.bind_lifecycle(...)` with stubs. Pre-stub `sys.modules["transport.server"]` with a namespace containing a mock `_steer_captain_checkin`. Cover: due captain entry (`next_fire_at` in past, `_ensure_crew_running` succeeds, no sentinel) → `_steer_captain_checkin` called and `next_fire_at` advanced. Verify: `tests/run.sh --unit` passes.

- [x] 5.2 Add captain monitor skip-path tests: `next_fire_at` in future → `_steer_captain_checkin` not called; `enabled: False` entry → skipped. Verify: `tests/run.sh --unit` passes.

- [x] 5.3 Add captain monitor sentinel auto-pause test: script `FakePodmanClient` to return a sentinel file for the crew's container → schedule entry `enabled` set to `False` and `_steer_captain_checkin` not called. Verify: `tests/run.sh --unit` passes.

- [x] 5.4 Add captain monitor failure test: `_ensure_crew_running` raises → `next_fire_at` advanced and `_steer_captain_checkin` not called. Verify: `tests/run.sh --unit` passes.

## 6. Integration check

- [x] 6.1 Run `tests/run.sh --unit` with all new tests together. Confirm no regressions in existing captain, monitor, sentinel, config, login, and registry lock tests.

## Workflow follow-up

- Archive the change after review.

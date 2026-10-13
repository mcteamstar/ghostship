# Tasks

## 1. _captain_monitor test class

- [x] 1.1 In `tests/unit/test_monitors.py` (or a new `tests/unit/test_captain_monitor.py`), add a `TestCaptainMonitor` class mirroring the existing `TestScheduleMonitor` structure. Mock `_steer_captain_checkin`, `_dispatch_captain_checkin`, `_ensure_crew_running`, and `_registry`. Cover: fire condition met (next_fire_at in past, crew running) → steer/dispatch called; fire condition not met → neither called; `_ensure_crew_running` raises → error logged, `next_fire_at` advances; `_steer_captain_checkin` returns 400 → fallback to dispatch, `current_task_id` cleared. Verify: `tests/run.sh --unit` passes.

## 2. _reseed_crew_schedules captain branch tests

- [x] 2.1 Add tests for `_reseed_crew_schedules` captain schedule branches (in existing reseed test file or `tests/unit/test_lifecycle_reseed.py`). Cover: no existing task → `_dispatch_captain_checkin` called; existing living task → no dispatch; session gone (task marked dead) → `_dispatch_captain_checkin` called and `current_task_id` cleared. Verify: `tests/run.sh --unit` passes.

## 3. _append_captain_mail I/O path tests

- [x] 3.1 Add tests for `_append_captain_mail` in `tests/unit/test_captain.py` (new or extend). Mock `container_exec` to capture the written mail content. Cover: signing secret present → mail contains `X-Admiral-Sig` header with valid HMAC; no signing secret → unsigned mail written (no `X-Admiral-Sig`). Verify: `tests/run.sh --unit` passes.
- [x] 3.2 Add tests for mailbox read helpers: `_mail_count`, `_read_all_mail_counts`, `_skim_all_mailboxes` using mock tar archive responses. Cover the empty-mailbox, single-message, and multi-message cases. Verify: `tests/run.sh --unit` passes.

## 4. _captain_do_order/status/stop branch tests

- [x] 4.1 Add tests for `_captain_do_order` covering: free-form message → `_append_captain_mail` called and registry updated; template resolution → correct template body delivered; active existing task → steer path taken. Mock `_append_captain_mail` and `_steer_captain_checkin`. Verify: `tests/run.sh --unit` passes.
- [x] 4.2 Add tests for `_captain_do_status`: enabled schedule → returns enabled=True and mailbox counts; disabled schedule → returns enabled=False. Add tests for `_captain_do_stop`: schedule disabled in registry and `enabled=False` returned. Verify: `tests/run.sh --unit` passes.

## 5. Integration check

- [x] 5.1 Run `tests/run.sh --unit` with all new tests together. Confirm no regressions in existing captain and monitor tests.

## Workflow follow-up

- Archive the change after review.

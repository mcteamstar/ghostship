# Proposal

**Plane ticket:** TRN-234

## Why

The captain subsystem — the core of ghostship's autonomous SDD workflow — has 0% test coverage on its most critical runtime paths. The 0.7.0 independent review (indy-070) flagged four distinct coverage gaps. The schedule and idle monitors both have test classes; the captain monitor does not. The `_append_captain_mail` I/O path, `_reseed_crew_schedules` captain branches, and `_captain_do_order/status/stop` sub-paths are all untested, meaning regressions in the most-used feature go undetected by CI.

## What Changes

- **TC-2 — `_captain_monitor` test class**: Mirror the existing `TestScheduleMonitor` and `TestIdleMonitor` pattern in `tests/unit/test_monitors.py`. Cover: fire condition met → `_steer_captain_checkin` dispatched; fire condition not met → skip; `_ensure_crew_running` failure → error logged, schedule advances; stale `current_task_id` cleared on fallback.
- **TC-5 — `_reseed_crew_schedules` captain branches**: Add tests for the three captain schedule type branches: no existing task → `_dispatch_captain_checkin`; existing task → verify liveness; session gone → re-dispatch. `tests/unit/test_lifecycle_reseed.py` or extend existing reseed tests.
- **TC-6 — `_append_captain_mail` I/O path**: Unit tests with mock `container_exec` covering: signing secret present → signed mail written; no signing secret → unsigned; related: `_mail_count`, `_read_all_mail_counts`, `_skim_all_mailboxes` with mock tar reads.
- **TC-7 — `_captain_do_order/status/stop` branch coverage**: Tests covering: template resolution → mail delivery → registry write-back; active-task steer branch in `do_order`; schedule-disable path in `do_stop`. Mock `_append_captain_mail` and registry.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transport-test-coverage`: add requirements for `_captain_monitor` test class, `_reseed_crew_schedules` captain branch tests, `_append_captain_mail` I/O tests, and `_captain_do_*` branch tests.

## Impact

- `tests/unit/test_monitors.py` — new `TestCaptainMonitor` class
- `tests/unit/test_captain.py` (new or extend) — mail I/O, `do_*` branches
- `tests/unit/test_lifecycle_reseed.py` (new or extend) — captain schedule branches
- No production code changes

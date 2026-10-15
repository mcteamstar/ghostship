# Proposal

**Plane ticket:** TRN-249

## Why

`transport/monitors.py` is the backbone of ghostship's autonomous runtime — the schedule monitor fires crew jobs, the idle monitor stops and restarts containers, and the captain monitor drives Raven check-ins — yet the module has no dedicated unit-test class. The independent review (indy-070) flagged this gap. Regressions in health monitoring, liveness checks, container status polling, and alerting/notification logic all go undetected by CI.

## What Changes

- **New file `tests/unit/test_monitors.py`** (or extend existing partial coverage): comprehensive unit tests for all three monitor loops and their helper functions.
- **`TestScheduleMonitor`**: covers job-firing logic, gateway-state sync, one-shot job teardown, disabled/due filter, `_ensure_crew_running` failure path.
- **`TestIdleMonitor`**: covers idle-stop decision tree — active tasks, cron activity, captain schedule hold, cookie-refresh path, TOCTOU guard, double-stop guard, `_stopping` flag lifecycle.
- **`TestCaptainMonitor`** (if not yet present): covers sentinel check auto-pause, fire/skip, `_steer_captain_checkin` failure fallback.
- **`TestCronActivityHelpers`**: pure-function tests for `_cron_activity_since` and `_cron_has_enabled_job`.
- **`TestIdleSkipReason`**: tests for `_note_idle_skip` — reason-change logging, same-reason deduplication.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transport-test-coverage`: add requirements for `_schedule_monitor`, `_idle_monitor`, and `_captain_monitor` unit-test classes, plus `_cron_activity_since`, `_cron_has_enabled_job`, and `_note_idle_skip` helper coverage.

## Impact

- `tests/unit/test_monitors.py` — new or extended test file (primary deliverable)
- No production code changes
- `openspec/specs/transport-test-coverage/spec.md` — delta spec adding monitor test requirements

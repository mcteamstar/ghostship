## Context

The captain subsystem consists of three source files (`transport/captain.py`,
`transport/monitors.py`, `transport/lifecycle.py`) and is exercised by
`tests/unit/test_captain.py` and `tests/unit/test_monitors.py`.  Existing test
coverage for schedule-monitor and idle-monitor is thorough; the captain-specific
runtime paths identified by the indy-070 review are absent.

Four gaps remain:

1. `_captain_monitor` (monitors.py line ~591) — the background loop that drives
   captain check-ins via dispatch+steer.  No `TestCaptainMonitor` class exists.
2. `_reseed_crew_schedules` captain branches (lifecycle.py ~1500) — the three
   branches for a captain-type schedule entry in the reseed pass (no task /
   living task / session gone).
3. `_append_captain_mail` I/O path (captain.py ~418) — the mail delivery helper
   that reads the signing secret, formats, and pipes through sendmail.
4. `_captain_do_order / _captain_do_status / _captain_do_stop` — the server-side
   action dispatch helpers that wrap around `_append_captain_mail` and registry
   writes.

The existing tests already validate the higher-level `server.captain()` MCP
tool, so these gaps are in the underlying runtime helpers that the tool
delegates to, not the tool boundary itself.

See proposal.md — Why.

## Goals / Non-Goals

**Goals:**

- Add a `TestCaptainMonitor` class mirroring `TestScheduleMonitor` /
  `TestIdleMonitor` structure.
- Cover the three captain branches in `_reseed_crew_schedules` (no task,
  living task, session gone → re-dispatch).
- Cover `_append_captain_mail` signing (secret present / absent) and the
  related mailbox read helpers.
- Cover `_captain_do_order`, `_captain_do_status`, `_captain_do_stop` execution
  paths end-to-end against mocked collaborators.

**Non-Goals:**

- No production code changes.
- No new e2e or integration tests — unit tests only.
- No changes to existing test classes.

## Decisions

### D1 — `TestCaptainMonitor` placement: add to `test_monitors.py`

`TestScheduleMonitor` and `TestIdleMonitor` both live in
`tests/unit/test_monitors.py`.  `_captain_monitor` is implemented in
`transport/monitors.py` (line ~591).  Placing `TestCaptainMonitor` in the same
file keeps monitor tests co-located with their module.

Alternatives considered:
- New file `tests/unit/test_captain_monitor.py` — the proposal mentions this as
  an option, but co-location in `test_monitors.py` matches the existing pattern
  with no overhead.

### D2 — `_captain_monitor` loop control: same `StopIteration`-on-sleep pattern

`TestScheduleMonitor` and `TestIdleMonitor` both break out of the `while True`
loop by raising `StopIteration` from a patched `time.sleep`.  The captain
monitor also calls `time.sleep` at the end of each iteration (via
`time.time() + _CAPTAIN_MONITOR_INTERVAL` → sleep calculation).
`TestCaptainMonitor` uses the same mechanism to control iteration count.

### D3 — Patch call sites, not library internals

Following the call-site patching principle documented in `test_captain.py`'s
module docstring:

- `_steer_captain_checkin` and `_dispatch_captain_checkin` are imported inside
  `_captain_monitor` from `server` at call time.  Patch them on `server` (the
  call-site module), not on `monitors`.
- `_ensure_crew_running` is injected via `bind_lifecycle()` into `monitors`.
  Patch it as `monitors._ensure_crew_running`.
- `_load_registry` / `_save_registry` / `_get_crew_schedules` / `_registry_lock`
  are imported directly into `monitors` from `registry`.  Patch them as
  `monitors._load_registry`, etc.

### D4 — `_reseed_crew_schedules` captain branches: test in `test_monitors.py` or `test_lifecycle.py`

`_reseed_crew_schedules` lives in `lifecycle.py`.  The existing reseed tests
(`ReseedCronReconcileTests`) are in `test_monitors.py` because that file imports
`lifecycle` via the helpers module.  New captain-branch tests join that class
or a sibling class in the same file.

### D5 — `_append_captain_mail` I/O tests: add to `test_captain.py`

`_append_captain_mail` is defined in `captain.py`.  `test_captain.py` already
imports `captain_mod`.  The new test class goes there.

The function reads the signing secret from `_read_crew_secret(crew_id)` (not
directly from `container_exec`).  Tests patch `captain_mod._read_crew_secret`
and `captain_mod._load_registry` to control signing secret and registry state.
They capture the payload delivered to `podman.container_exec_checked` to assert
on the formatted mail content.

### D6 — `_captain_do_order/status/stop` tests: add to `test_captain.py`

`_captain_do_order`, `_captain_do_status`, and `_captain_do_stop` are thin
helpers exposed from `server.py` (imported/re-exported via the captain module
boundary).  The existing `CaptainStandingOrdersTests` tests the public
`server.captain()` MCP tool which calls these helpers.  The new tests exercise
the helpers more directly, mocking `_append_captain_mail` and `_load_registry`
at the `server` call-site level (consistent with D3).

## Risks / Trade-offs

[Fragility of `StopIteration` loop-break pattern] → The captain monitor's inner
`while True` loop has a try/except that catches `Exception`.  `StopIteration`
is not a subclass of `Exception` in Python 3, so it propagates out correctly.
However if the monitor ever wraps the sleep in a broad `BaseException` catch,
the test pattern breaks silently.  Mitigation: keep the pattern and document
it; the existing monitor tests use the same convention with no issues.

[Import-at-call-time for `_steer_captain_checkin`] → `_captain_monitor` imports
`_steer_captain_checkin` inside the loop body (to break a module load cycle).
Tests that patch `server._steer_captain_checkin` will work correctly only if
the patch is applied before the inner import runs.  Using `patch.object(server,
"_steer_captain_checkin", ...)` as a context manager wrapping the monitor call
satisfies this because Python's import cache returns the already-imported `server`
module, and `patch.object` replaces the attribute on that cached module object
before the monitor references it.  No special ordering is needed.

[`_reseed_crew_schedules` "living task" verification] → The "existing living
task → no dispatch" branch calls `_crew_api_with_recovery` to check liveness.
The three branches share one function; the test must supply a side_effect
sequence that distinguishes the three scenarios.  Mitigation: each scenario
is tested in an independent test method with its own mocked registry and
`_crew_api_with_recovery` response.

## Migration Plan

No migration.  All changes are additive test code.  Deployment: tests run on
the standard `tests/run.sh --unit` invocation; no schema or config changes.

Rollback: any test regression is caught in CI before merge; the tests
themselves have no runtime impact if deleted.

## Open Questions

None.  All branch paths are observable through existing function signatures and
mock-able collaborators.

## Why

A Banshee test-quality review of `transport/test_transport.py` found tests that
shadow the production code they purport to exercise (inline re-implementations
instead of calling the real function), missing coverage for two bugs fixed in
TRN-37, and several gaps in medium-priority paths. Left unaddressed these tests
can pass while the production code is broken — the very failure mode a test suite
must prevent.

## What Changes

- **ScheduleMonitorTests.test_monitor_wakes_crew_and_fires_tick** — rewrite to
  drive the real `_schedule_monitor` function instead of inlining its loop.
  Use `StopIteration` on `time.sleep` to break out after one iteration.
- **TestMemoryGate.test_gate_skipped_when_disabled** — replace the
  copy-pasted production guard with a direct call to `_ensure_crew_running`
  and verify via observable side-effects (no system_info call).
- **ScheduleCancelTests.test_cancel_success** — seed a registry entry and
  assert it is removed after cancellation, exercising the TRN-29 cleanup path.
- **AdvanceNextFireAtTests** (new class) — zero-to-coverage for the
  `_advance_next_fire_at` cron branch; verify TRN-37 fix (correct cron interval,
  not always +60 s).
- **RegistrySerialisation test** — add `json.dumps(..., allow_nan=False)` test
  to catch `float("inf")` slipping into the saved registry; verifies TRN-37 fix.
- **ScheduleListTests** — add backward-compat fallback test (gateway path
  exercised when registry has no entries for the crew).
- **CaptainOrderTests / SchedulePersistenceTests** — add assertion that
  `next_fire_at` is set to `time.time() + interval` on captain resume.
- **ReconcileRegistryTests** — add test verifying `_reseed_crew_schedules` is
  called and re-registers jobs when schedules are present on reconcile restart.
- **IdleMonitorTests** — add test for cron-endpoint 401 retry path (separate
  from the existing spawn 401 test).
- **Housekeeping** — add `ScheduleMonitorTests` and `SchedulePersistenceTests`
  to the portability header; fix `test_timeout_expires` to use
  `assertAlmostEqual` instead of `assertLess`; replace `LoginGuardClearTests`
  source-inspection test with a behavioural assertion.

No production code is modified.

## Capabilities

### New Capabilities
<!-- None — pure test file change -->

### Modified Capabilities
<!-- No spec-level behaviour changes. skip_specs: true -->

## Impact

- **File changed**: `transport/test_transport.py` only.
- **Dependencies**: TRN-37 must be merged before the `_advance_next_fire_at`
  cron test and the `float("inf")` serialisation test can pass (they verify
  TRN-37 fixes). Tasks that depend on TRN-37 are marked accordingly.
- No API, configuration, or runtime behaviour changes.

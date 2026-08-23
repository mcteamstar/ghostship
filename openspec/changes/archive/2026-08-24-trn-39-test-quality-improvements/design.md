## Context

See `proposal.md — Why` for motivation. The single file in scope is
`transport/test_transport.py` (4 515 lines). All ten findings operate
independently — they are in distinct test classes and touch no shared
state — so they can be implemented in any order. Two findings (cron branch
of `_advance_next_fire_at`, `float("inf")` serialisation) verify TRN-37
fixes and must not be merged before TRN-37.

## Goals / Non-Goals

**Goals:**
- Each test calls the production function it claims to test (no inline copies).
- New tests cover the previously-uncovered paths identified by Banshee.
- Portability header is accurate.
- Housekeeping items are closed.

**Non-Goals:**
- No changes to production code (`server.py` or any other module).
- No new test infrastructure (no new fixtures, helpers, or conftest).
- TRN-37 fixes themselves are not part of this change.

## Decisions

**D1 — Drive `_schedule_monitor` via `StopIteration` on `time.sleep`**

The current test inlines the monitor loop body, so it exercises copy-pasted
logic rather than the real function. The fix patches `time.sleep` to raise
`StopIteration` on first call, which exits the `while True:` loop in
`_schedule_monitor` cleanly after exactly one iteration. All other patches
(registry, crew API, save) stay the same. Alternative considered: patch
`time.time` to advance past a deadline — rejected because `_schedule_monitor`
has no deadline; it loops forever until the thread is stopped.

**D2 — Drive `_ensure_crew_running` directly for the disabled-gate test**

The test currently copies the guard `if server.GA_MIN_FREE_MEM_GB > 0` from
production into the test. The fix calls `_ensure_crew_running` with
`GA_MIN_FREE_MEM_GB = 0.0` and verifies that `_wait_for_memory` was never
called (via `assert_not_called`). This confirms the guard lives in the
production function, not the test.

**D3 — Seed registry entry in `test_cancel_success`, assert removal**

The TRN-29 cancel path removes the entry from the transport registry after
the gateway DELETE. The existing test patches `_load_registry` to return
`{"crews": {}}`, so the cleanup branch never runs. Fix: seed a registry
entry with a matching `job_id` and assert it is absent from the saved
registry after cancellation.

**D4 — New `AdvanceNextFireAtTests` class for the cron branch**

`_advance_next_fire_at` has zero tests for the `cron_expr` branch. A minimal
class with three methods covers: interval branch (baseline), cron branch
(TRN-37 fix — must produce a value significantly greater than `now + 60`),
and one-shot branch (sets `float("inf")`). The cron test is annotated with a
`# requires TRN-37` comment and will fail before that change is merged.

**D5 — `float("inf")` serialisation test in `SchedulePersistenceTests`**

Add `test_registry_rejects_inf_in_next_fire_at`: build a registry dict with
`next_fire_at=float("inf")`, call `json.dumps(..., allow_nan=False)`, and
assert it raises `ValueError`. This confirms the guard added by TRN-37 is
the right call-site fix. Annotated `# requires TRN-37`.

**D6 — `_schedule_list` backward-compat test**

Add a test in `ScheduleListTests` (or a new `ScheduleListFallbackTests`) that
patches `_get_crew_schedules` to return `[]` and verifies the gateway
`/api/crons` path is hit. This is a pure unit test using existing mocks.

**D7 — Captain resume `next_fire_at` assertion**

In `SchedulePersistenceTests.test_captain_order_writes_schedule_entry` (or a
new sibling), after calling `captain(action="order", ...)`, read the saved
registry and assert `schedule_entry["next_fire_at"] >= time.time() + interval - 1`
(allowing one second of clock drift). This is already exercised by the
existing test structure; the assertion just needs to be added.

**D8 — `_reseed_crew_schedules` on reconcile restart**

`ReconcileRegistryTests` has no test for the reconcile path that calls
`_reseed_crew_schedules`. Add a test that seeds a registry with one
schedule and calls the reconcile code path (or directly calls
`_reseed_crew_schedules`), then asserts that the gateway `/api/crons` POST
was made for the missing job.

**D9 — Cron 401 retry in `_idle_monitor`**

`IdleMonitorTests` tests the spawn-endpoint 401 path. Add a parallel test
for the cron-endpoint 401 path: patch the first cron GET to return 401,
patch `_mint_cookie` to return a fresh cookie, and assert the second cron GET
is made with the new cookie.

**D10 — Housekeeping**

- Portability header: insert `ScheduleMonitorTests, SchedulePersistenceTests`
  into the "Portable" list (alphabetically consistent with the existing entries).
- `test_timeout_expires`: the assertion `self.assertLess(result, 2.0)` is
  correct in intent but `assertAlmostEqual(result, expected, delta=0.1)` is
  more precise and self-documenting; use it.
- `LoginGuardClearTests.test_guard_clear_ordering_verified`: replace
  `inspect.getsource` string search with a test that mocks
  `_nuke_login_container` to set a flag, then asserts `_login_pending` is
  `None` only *after* the flag was set. This tests ordering without coupling
  to source text.

## Risks / Trade-offs

**[Risk] StopIteration threading** — raising `StopIteration` from a mock
inside a `while True:` loop is idiomatic in Python unit tests, but care is
needed that the `StopIteration` propagates to the thread's entry point and
not silently into a generator. `_schedule_monitor` is not a generator, so
this is safe. Mitigation: verify the thread exits within a short join timeout
in the test.

**[Risk] TRN-37 dependency** — two tests will fail on `main` until TRN-37
merges. Mitigation: annotate those tests with `# requires TRN-37` and note
the dependency explicitly in `tasks.md`. They should not be merged before
TRN-37.

**[Risk] Clock sensitivity in `next_fire_at` assertions** — wall-clock
comparisons can be flaky on slow CI. Mitigation: use a `±1` second tolerance
or patch `time.time` to return a fixed value before calling the function under
test.

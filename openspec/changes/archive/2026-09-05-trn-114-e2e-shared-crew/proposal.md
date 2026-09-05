# TRN-114: Share a single crew across all stateless e2e test classes

## Why

TRN-112 reduced e2e launch count from ~11 to ~5 and introduced parallel test
execution. The measured wall time remained ~6 min because launching 4–5 crews
concurrently saturates gateway readiness capacity on the host — one crew failed
to become ready within 30s during the run. Crew lifecycle cost (~30s cold start)
is the dominant factor; test execution time is negligible by comparison. The fix
is to stop tearing down and re-launching a crew per test class: a crew is cheap
to reuse and expensive to replace.

## What Changes

- **Replace per-class crews with a module-level shared crew** — a single
  `e2e-shared` crew is launched once per test file via `setUpModule` /
  `tearDownModule`, shared across all test classes in that file whose tests do
  not mutate crew-level state. The shared crew is never torn down between
  classes; only the module teardown nukes it.
- **TestDispatchPickup, TestSupplyEvac, TestScheduleTool, TestResponseSchemas,
  and the stateless tests in TestErrorPaths** all migrate to the shared crew.
  Their `setUpClass` / `tearDownClass` hooks are removed; the class body reads
  `CREW_ID` from a module-level constant.
- **TestSteerTool** keeps its own crew: it dispatches a long-running task and
  steers it; a shared task stream would make assertions ambiguous.
- **TestErrorPaths lifecycle tests** (`test_pickup_nonexistent_task`,
  `test_launch_duplicate_crew`, `test_nuke_without_confirm`) keep their own
  short-lived throw-away crews within the test method body — these are 3 of the
  cheapest launches and cannot share state.
- **TestCrewLifecycle** and **TestCaptainStatusStoppedCrew** are inherently
  stateful and unchanged.
- **Parallel runner** continues to be used; with 2 test files each holding one
  shared crew, `unittest-parallel` runs them as 2 workers — no concurrent
  launches against the same host.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `transport-test-coverage`: e2e suite fixture model; module-level shared crew
  pattern; launch count reduction.

## Impact

- `tests/e2e/test_transport_e2e.py` — add `setUpModule` / `tearDownModule` and
  `SHARED_CREW_ID` constant; remove `setUpClass` / `tearDownClass` from
  `TestDispatchPickup` and `TestSupplyEvac`; update `CREW_ID` references to
  `SHARED_CREW_ID`.
- `tests/e2e/test_transport_e2e_extended.py` — add `setUpModule` /
  `tearDownModule` and `SHARED_CREW_ID` constant; remove `setUpClass` /
  `tearDownClass` from `TestScheduleTool`, `TestResponseSchemas`, and the
  stateless portion of `TestErrorPaths`; `TestSteerTool` keeps its own
  `setUpClass` / `tearDownClass`; `TestErrorPaths` lifecycle tests keep their
  per-method throw-away crews.
- `tests/e2e/helpers.py` — no changes expected.
- `tests/run.sh` — no changes needed; parallel runner already wired.

## Target

Cut total e2e launches from ~5 to ~3 (one shared per file + steer + lifecycle
throw-aways). Eliminate concurrent gateway pressure. Wall time target ~2 min.

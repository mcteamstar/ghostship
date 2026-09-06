# Design: trn-114-e2e-shared-crew

## Context

See proposal.md — Why for motivation.

After TRN-112, the e2e suite has two test files:

- `test_transport_e2e.py` — `TestHealthCheck`, `TestCrewLifecycle`,
  `TestDispatchPickup`, `TestSupplyEvac`, `TestAuthGate`, `TestKiroAuthCycle`
- `test_transport_e2e_extended.py` — `TestErrorPaths`, `TestScheduleTool`,
  `TestSteerTool`, `TestResponseSchemas`, `TestAuthExtended`,
  `TestCaptainStatusStoppedCrew`

With TRN-112, `TestDispatchPickup`, `TestSupplyEvac`, `TestScheduleTool`,
`TestSteerTool`, `TestResponseSchemas`, and `TestErrorPaths` each own a
`setUpClass`/`tearDownClass` pair. `unittest-parallel` runs the two files as
workers in parallel — all their `setUpClass` launches fire concurrently,
saturating the host.

## Goals / Non-Goals

**Goals:**
- One shared crew per file for all stateless test classes
- Zero concurrent crew launches during the parallel run
- Test isolation preserved: no class can observe another class's tasks or jobs

**Non-Goals:**
- Sharing a crew across both files (adds cross-worker coordination complexity
  not worth the single extra launch it saves)
- Changing `TestHealthCheck`, `TestAuthGate`, `TestAuthExtended`,
  `TestKiroAuthCycle` (no crew needed)
- Changing the parallel runner configuration in `run.sh`

## Decisions

### Decision 1: `setUpModule` / `tearDownModule` as the shared fixture

`unittest` provides `setUpModule()` and `tearDownModule()` as module-level
hooks that run exactly once per file, before and after all test classes in
that file. This is the correct scope: one crew per worker, zero per-class
launch overhead for stateless classes.

Alternative considered: a module-level singleton with lazy init inside
each `setUpClass`. Rejected — it pushes teardown logic into every class and
makes it easy to forget teardown in new test classes added later.

### Decision 2: Module-level `SHARED_CREW_ID` constant

A single constant (`SHARED_CREW_ID = "e2e-shared-main"` /
`"e2e-shared-extended"`) is defined at module level. Stateless classes set
`CREW_ID = SHARED_CREW_ID` as their class attribute. This keeps the
`CREW_ID` reference pattern unchanged in test bodies while removing the
per-class launch machinery.

Alternative considered: passing crew_id via a module-level dict. Rejected —
more complex than a constant.

### Decision 3: `TestErrorPaths` loses its `setUpClass`/`tearDownClass`

`TestErrorPaths` in TRN-112 gained a class-level `e2e-err-shared` crew.
With TRN-114 it instead uses `SHARED_CREW_ID` from `setUpModule`. The three
lifecycle tests (`test_pickup_nonexistent_task`, `test_launch_duplicate_crew`,
`test_nuke_without_confirm`) keep their own short-lived per-method crews with
distinct names (`e2e-err-pickup`, `e2e-err-dup`, `e2e-err-noconfirm`).

### Decision 4: `TestSteerTool` keeps its own crew

`TestSteerTool` dispatches a long-running task and steers it mid-flight.
Using the shared crew would pollute its task list, making elapsed-time and
done-status assertions ambiguous. The one extra launch is justified.

### Decision 5: Shared crew names

- `test_transport_e2e.py` → `SHARED_CREW_ID = "e2e-shared-main"`
- `test_transport_e2e_extended.py` → `SHARED_CREW_ID = "e2e-shared-ext"`

Distinct names prevent collision if both workers happen to run `setUpModule`
before either runs `tearDownModule` (no restart ordering guarantee).

## Risks / Trade-offs

**Risk: Shared crew accumulates tasks/jobs across classes, polluting `pickup` list assertions**
→ Mitigation: `TestResponseSchemas.test_pickup_list_shape` asserts `"tasks" in result` and `"mail_summary" in result`, not specific task counts. `TestScheduleTool` creates and cancels its own named job within each test. No assertion relies on the crew being empty.

**Risk: `setUpModule` failure skips all tests in the file, not just one class**
→ This is acceptable. If the shared crew cannot be launched, all dependent tests should be skipped/errored — a whole-file failure is less misleading than per-class failures with confusing error messages.

**Risk: A test leaves state on the shared crew that breaks a later test in the same file**
→ Mitigation: stateless classes only dispatch tasks or jobs scoped to their own `task_id`/`job_id`. `TestScheduleTool` cancels its job in teardown. `TestDispatchPickup` reads a specific `task_id`. No class queries global state in a way that depends on crew emptiness.

## Migration Plan

1. Add `SHARED_CREW_ID` constant and `setUpModule` / `tearDownModule` to each test file
2. Remove `setUpClass` / `tearDownClass` from `TestDispatchPickup`, `TestSupplyEvac` in `test_transport_e2e.py`
3. Remove `setUpClass` / `tearDownClass` from `TestScheduleTool`, `TestResponseSchemas`, `TestErrorPaths` in `test_transport_e2e_extended.py`; update `TestErrorPaths` to use `SHARED_CREW_ID`
4. `TestSteerTool` `setUpClass`/`tearDownClass` unchanged
5. Update all `CREW_ID` class attributes that previously launched their own crew to `CREW_ID = SHARED_CREW_ID`
6. Verify no test body references a local `crew_id` variable that should now be `SHARED_CREW_ID`

Rollback: revert the two test files. No transport or infrastructure changes.

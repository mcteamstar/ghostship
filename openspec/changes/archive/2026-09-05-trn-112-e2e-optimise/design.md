## Context

See proposal.md — Why, for motivation. The current e2e test structure is summarised below as the baseline the changes operate on.

**Current crew-launch count per full `--e2e` run (both test files, serial):**

```
test_transport_e2e.py
  TestHealthCheck          — 0 launches (HTTP only)
  TestCrewLifecycle        — 1 crew, setUp/tearDown (1 launch per test × 1 test = 1)
  TestDispatchPickup       — 1 crew, setUp/tearDown (1 launch per test × 1 test = 1)
  TestSupplyEvac           — 1 crew, setUp/tearDown (1 launch per test × 1 test = 1)
  TestAuthGate             — 0 launches
  TestKiroAuthCycle        — 0 launches

test_transport_e2e_extended.py
  TestErrorPaths           — 0 shared crew + 3 per-test throw-aways = 3 launches
  TestScheduleTool         — 1 crew, setUp/tearDown (1 launch per test × 2 tests = 2)
  TestSteerTool            — 1 crew, setUp/tearDown (1 launch per test × 2 tests = 2)
  TestResponseSchemas      — 1 class-level crew + 1 redundant in test_launch_response_shape = 2

Total: ~12 launches × ~30s ≈ 6 min
```

**Target after this change (serial):**

```
  TestCrewLifecycle        — 1  (unchanged)
  TestDispatchPickup       — 1  (class-level)
  TestSupplyEvac           — 1  (class-level)
  TestErrorPaths           — 1  (class-level) + 3 per-method throw-aways = 4  *see note
  TestScheduleTool         — 1  (class-level)
  TestSteerTool            — 1  (class-level)
  TestResponseSchemas      — 1  (class-level, no second launch)

Total serial: ~10 launches × ~30s ≈ 5 min
With unittest-parallel (classes run concurrently): critical-path ≈ longest class ≈ 1–2 min
```

*Note on TestErrorPaths: the 3 per-method throw-away crews are inherently sequential within the method and cannot be eliminated — they test lifecycle-mutating operations. They add ~90s serial but run concurrently with other classes under `unittest-parallel`.

## Goals / Non-Goals

**Goals:**
- Reduce full e2e suite wall time from ~5–6 min to ~1–2 min.
- No reduction in test coverage — all existing test assertions are preserved.
- `unittest-parallel` is a soft dependency: absent package → silent serial fallback, not a broken run.
- `TestCrewLifecycle` behaviour is unchanged — it tests the lifecycle and must stay per-test.

**Non-Goals:**
- Changing test assertions or coverage scope.
- Parallelising unit or integration suites (not in scope; unit suite is already fast).
- Migrating from `unittest` to `pytest` or any other framework.
- Changing the transport itself, only the test harness.

## Decisions

### Decision: setUpClass/tearDownClass for four test classes

`TestDispatchPickup`, `TestSupplyEvac`, `TestScheduleTool`, and `TestSteerTool` each contain only tests that operate on a single crew without leaving persistent state that bleeds across test methods. For example, `TestScheduleTool.test_cancel_nonexistent_job` cancels a job that does not exist — the crew itself is unchanged. `TestDispatchPickup.test_dispatch_and_pickup` dispatches a task but does not modify the crew's configuration or leave data that would affect a second test.

Conversion is mechanical: rename `setUp` → `setUpClass`, `tearDown` → `tearDownClass`, prefix `self.CREW_ID` references with `cls.` or `self.__class__.`, and replace `self.assertEqual(result.get("status"), "ready")` with a class-level `RuntimeError` raise (matching the existing `TestResponseSchemas.setUpClass` pattern).

**Alternative considered — new isolated crew per test method via `addCleanup`:** would preserve full isolation but add no benefit for tests that provably don't share state, while still paying the per-launch cost.

### Decision: TestErrorPaths — one shared class crew, three per-method throw-aways

The five stateless tests (`test_nuke_nonexistent_crew`, `test_dispatch_nonexistent_crew`, `test_evac_nonexistent_crew`, plus the shared-crew parts of the three lifecycle tests) need only a live crew to assert "not found" paths. The three lifecycle-mutating tests need their own crews because:

- `test_pickup_nonexistent_task` needs a real crew to verify pickup returns an error for an unknown task_id.
- `test_launch_duplicate_crew` launches a second copy of the same crew_id to verify the "already exists" error.
- `test_nuke_without_confirm` launches a crew, calls nuke with `confirm=False`, and verifies the crew survives.

The shared class crew uses CREW_ID `"e2e-err-shared"`. The three per-method crews use distinct names: `"e2e-err-pickup"`, `"e2e-err-dup"`, `"e2e-err-noconfirm"` (matching existing names already in the test file).

**Alternative considered — make all five stateless tests use the non-existent phantom `GHOST_CREW`:** already done for three of them (`nuke_nonexistent`, `dispatch_nonexistent`, `evac_nonexistent`). Those three need no crew at all; they call a non-existent `crew_id`. Only the remaining two genuinely need a live crew for different reasons.

### Decision: TestResponseSchemas — store launch result on cls, reuse in test_launch_response_shape

`setUpClass` already launches `cls.CREW_ID = "e2e-schema"` and stores the result implicitly. `test_launch_response_shape` currently launches a *second* crew (`"e2e-schema-shape"`) to get a "clean" launch response. This is unnecessary — the `setUpClass` response is available as `cls._launch_result` if we store it. The shape assertions (checking `crew_id`, `status`, `container`, `gateway_url`) are equally valid against the already-running crew.

Implementation: in `setUpClass`, do `cls._launch_result = _mcp_call("launch", crew_id=cls.CREW_ID)` instead of discarding the return value. In `test_launch_response_shape`, assert against `self.__class__._launch_result` instead of launching `"e2e-schema-shape"`.

**Alternative considered — keep the second launch, it proves launch is idempotent-free:** The existing test name is `test_launch_response_shape`, not a uniqueness test. The second crew was added to guarantee a "fresh" response. Since `setUpClass` already records one, it is redundant.

### Decision: Shorten TestSteerTool sleep task from 60s to 25s

The steer test dispatches a task that sleeps so it is still running when the steer call arrives. 60s guarantees the task is running but adds 60s to the class's wall time even after the setUp/tearDown → setUpClass conversion. 25s is sufficient: the agent startup + first tool call takes ~10–15s, so the steer call will arrive well before 25s elapses. The test polls for `elapsed_secs > 0` with a 30s deadline, which still holds at 25s.

**Alternative considered — use a different long-running task (e.g., a sleep loop):** 25s is simpler and more readable than a shell loop inside the task string.

### Decision: unittest-parallel pinned to 1.8.6

`1.8.6` is the current latest. Pin exact (`==1.8.6`) to match the existing requirements.txt convention (all other packages are exact-pinned). The package is a thin wrapper around `concurrent.futures` and has no heavy transitive dependencies.

**Invocation in run.sh:** `python -m unittest_parallel -s tests/e2e -p "test_*.py" -t .`. The module name is `unittest_parallel` (underscore), which is the correct `python -m` entry point for this package. A `python -c "import unittest_parallel"` availability check before the invocation decides whether to use parallel or serial.

**Alternative considered — `pytest-xdist`:** heavier dependency, requires migrating to pytest runner, out of scope.

### Decision: Serial fallback is silent (no warning)

If `unittest-parallel` is absent, `run.sh` silently uses the serial runner. A warning would be noise in environments where the package is intentionally not installed (e.g., minimal CI images running only `--unit`). The venv bootstrap in `run.sh` will always install `unittest-parallel` when it installs from `transport/requirements.txt`, so absence only happens if someone invokes `run.sh` against a system Python or a custom venv. Fail-open is the right default.

## Risks / Trade-offs

[Risk: class-level crew fails to start; all tests in the class are skipped rather than failed] → Mitigation: `setUpClass` raises `RuntimeError` on non-ready status, which `unittest` records as an error (not a skip) for the whole class — same pattern already used in `TestResponseSchemas`. Ghost can see the error in the test output.

[Risk: test ordering within a class causes state bleed when parallelism is added] → Mitigation: `unittest-parallel` dispatches at the *class* level, not the method level — all methods of a class run serially within the same worker process. Intra-class ordering is unchanged.

[Risk: 25s sleep not long enough on a slow host] → Mitigation: the test polls for `elapsed_secs > 0` with a 30s deadline before calling steer. If the agent hasn't started in 30s on a slow host, the test fails with a clear message ("Task never started within 30s") — same as today, but the poll window is unchanged.

[Risk: unittest-parallel exit code not propagated correctly] → Mitigation: `run.sh` uses `set -uo pipefail` and captures category exit codes explicitly via `run_category`. `python -m unittest_parallel` exits non-zero on any test failure (same contract as `python -m unittest`). No special handling needed.

## Migration Plan

No deployment migration needed — this change is entirely within the test harness. The production transport is not touched. The steps are:

1. Add `unittest-parallel==1.8.6` to `transport/requirements.txt`.
2. Edit `tests/e2e/test_transport_e2e.py` — convert `TestDispatchPickup` and `TestSupplyEvac`.
3. Edit `tests/e2e/test_transport_e2e_extended.py` — convert `TestErrorPaths`, `TestScheduleTool`, `TestSteerTool`, `TestResponseSchemas`.
4. Edit `tests/run.sh` — add parallel-runner detection and invocation under `--e2e`.

Rollback: revert the four files. No schema changes, no data migrations, no service restarts.

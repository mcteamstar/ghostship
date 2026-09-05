## Why

The e2e test suite launches ~10–11 crew containers across test classes (~30s per launch), totalling 5–6 minutes for a full run. Most of that time is pure overhead: test classes that perform no cross-test state mutation still tear down and re-launch their crew between every individual test method. Consolidating per-test setUp/tearDown to per-class setUpClass/tearDownClass, eliminating a redundant second launch in `TestResponseSchemas`, shortening a deliberate long-sleep task, and adding parallel test execution via `unittest-parallel` will cut the full suite runtime to ~1–2 minutes.

## What Changes

- **TestDispatchPickup**: convert `setUp`/`tearDown` to `setUpClass`/`tearDownClass` — no test in this class mutates shared crew state between tests, so one crew for the whole class is safe.
- **TestSupplyEvac**: same conversion — single upload/download round-trip per test, no cross-test state.
- **TestScheduleTool**: same conversion — create/list/cancel tests against a fresh named job each time, crew itself is unchanged.
- **TestSteerTool**: same conversion; also shorten the long-sleep task from "Wait 60 seconds" to "Wait 25 seconds" to reduce per-test wall time.
- **TestErrorPaths**: use a single shared class-level crew for the five stateless error-path tests; the three tests that inherently need their own throw-away crew (`test_pickup_nonexistent_task`, `test_launch_duplicate_crew`, `test_nuke_without_confirm`) keep their own per-method launch/nuke with distinct names, cleaned up inside the test method.
- **TestResponseSchemas**: store the `setUpClass` launch result on `cls` and use it inside `test_launch_response_shape` instead of launching a second crew.
- **TestCrewLifecycle**: no change — this class IS the launch→verify→nuke→verify lifecycle test; it must stay per-test.
- **`unittest-parallel`** added to `transport/requirements.txt` (pinned exact version); `tests/run.sh` wires it in under `--e2e` with a serial fallback when the package is absent.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `test-orchestration`: e2e suite execution now supports parallel test-class dispatch via `unittest-parallel`; the orchestrator (`tests/run.sh`) must detect availability and select the parallel runner under `--e2e`.

## Impact

- `tests/e2e/test_transport_e2e.py` — `TestCrewLifecycle` (unchanged), `TestDispatchPickup`, `TestSupplyEvac`, `TestAuthGate`, `TestKiroAuthCycle` (last two touch no crew lifecycle): convert setUp/tearDown to setUpClass/tearDownClass in `TestDispatchPickup` and `TestSupplyEvac`.
- `tests/e2e/test_transport_e2e_extended.py` — `TestErrorPaths` (shared class crew + per-method throw-aways for three tests), `TestScheduleTool` (class-level crew), `TestSteerTool` (class-level crew + shorter sleep), `TestResponseSchemas` (store launch result on `cls`).
- `transport/requirements.txt` — add `unittest-parallel==<pinned>`.
- `tests/run.sh` — `--e2e` path: run via `python -m pytest_parallel` / `unittest-parallel` when available; serial fallback via `python -m unittest discover`.

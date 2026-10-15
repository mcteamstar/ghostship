## Why

`transport/lifecycle.py` is the largest and most critical module in the transport layer (~3,200 lines) but has zero dedicated unit tests. The module manages the entire crew container lifecycle — creation, startup, recovery, config injection, teardown — and its bugs have direct production impact. Adding a focused unit test file closes the largest test-coverage gap in the transport suite.

## What Changes

- Add `tests/unit/test_lifecycle.py` — a new unit test module covering crew lifecycle management using `FakePodmanClient` and the existing conftest stubs.
- Tests cover the four top-level operations: create (via `launch` → `_finish_crew_setup`), start (via `ensure_running` / `_ensure_crew_running`), stop (via `_cleanup_crew` partial teardown), and destroy (via `nuke` → `_cleanup_crew` full teardown).
- Tests cover the state-transition graph: `launching` → `running`, `running` → `stopped`, `stopped` → `running` (restart), and `running` → removed (nuke).
- Tests cover the concurrency serialisation in `CrewLauncher.ensure_running`: leader/waiter pattern, generation counter, `_NUKED_DURING_RESTART` sentinel, and waiter propagation of leader exceptions.
- Tests cover resource gates: active-crew limit and memory gate blocking a restart.

## Capabilities

### New Capabilities

- `transport-test-lifecycle`: Unit test coverage for `transport/lifecycle.py` crew lifecycle operations (create, start, stop, destroy) and state transitions. Extends the existing `transport-test-coverage` spec with a dedicated per-module spec for the lifecycle module.

### Modified Capabilities

- `transport-test-coverage`: Add lifecycle module coverage requirements to the existing transport test-coverage spec.

## Impact

- **New file**: `tests/unit/test_lifecycle.py` (~400–600 lines).
- **No production code changes** — test only.
- **Dependencies**: Uses `FakePodmanClient` (already in `tests/fakes.py`), conftest stubs (already in `tests/unit/conftest.py`), and `unittest.mock.patch` for module-level globals in `lifecycle.py`.
- **CI**: The new file runs as part of the existing `pytest tests/unit/` invocation; no changes to `tests/run.sh` or CI config needed.

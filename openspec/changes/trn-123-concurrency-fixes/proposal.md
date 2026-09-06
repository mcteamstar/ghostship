## Why

Two shared mutable data structures in the transport server are written from both the asyncio event loop and background worker threads without any mutual-exclusion, creating data races that can silently corrupt task-timestamp records and the dashboard port→crew mapping. Additionally, the probe-then-stop sequence inside `_ensure_crew_running` is not serialised per-crew, allowing concurrent callers to race past the liveness check and each attempt `container_start`, resulting in duplicate container start calls and potential gateway state corruption.

## What Changes

- Add a `threading.Lock` (`_task_timestamps_lock`) guarding all read-modify-write access to `_task_timestamps` in `transport/server.py`.
- Add a `threading.Lock` (`_dashboard_port_crew_lock`) guarding all read-modify-write access to `_dashboard_port_crew` in `transport/server.py`.
- Add a per-crew `asyncio.Lock` registry (`_ensure_running_locks`, guarded by `_ensure_running_locks_lock`) so that concurrent callers to `_ensure_crew_running` in `transport/lifecycle.py` for the same crew_id are serialised through the probe-then-start sequence, preventing double `container_start`.
- Add unit tests covering the new lock paths in `tests/unit/test_server.py` and `tests/unit/test_lifecycle.py`.

## Capabilities

### New Capabilities

None — this is a pure concurrency hardening change with no user-visible behaviour changes.

### Modified Capabilities

- `crew-lifecycle`: The `_ensure_crew_running` function gains per-crew serialisation of the probe-then-start sequence. The externally observable contract (start a stopped crew before returning an updated crew dict) is unchanged; the fix eliminates a race that could trigger two `container_start` calls for the same crew under concurrent access.
- `task-timestamps`: The in-memory `_task_timestamps` dict gains a `threading.Lock` guard. The externally observable fields (`created_at`, `started_at`, `completed_at`) are unchanged; the fix eliminates a data race between the asyncio event loop (dispatch writes) and worker threads (pickup reads/updates).

## Impact

- `transport/server.py`: `_task_timestamps` and `_dashboard_port_crew` get explicit lock guards on every access site.
- `transport/lifecycle.py`: `_ensure_crew_running` acquires a per-crew asyncio lock for the "is running?" → "start" critical section.
- `tests/unit/test_server.py`: new concurrent-write tests for `_task_timestamps` and `_dashboard_port_crew`.
- `tests/unit/test_lifecycle.py`: new concurrent-call test for `_ensure_crew_running` ensuring `container_start` is called exactly once under concurrent callers.
- No API surface changes; no config changes; no dependency additions (locks from the standard library only).

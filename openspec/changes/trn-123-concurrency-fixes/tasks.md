## 1. Lock `_task_timestamps` (transport/server.py)

- [ ] 1.1 Add `_task_timestamps_lock = threading.Lock()` alongside `_task_timestamps` at module level in `transport/server.py`.
- [ ] 1.2 Wrap the `dispatch` write (`_task_timestamps[task_id] = {...}`) with `with _task_timestamps_lock`.
- [ ] 1.3 Wrap the `_dispatch_batch` loop write (`_task_timestamps[tid] = {...}`) with `with _task_timestamps_lock`.
- [ ] 1.4 Wrap the `_pickup_single` read-modify-write block (the `ts = _task_timestamps.get(...)` → `ts["started_at"] = ...` / `ts["completed_at"] = ...` sequence) with `with _task_timestamps_lock`.
- [ ] 1.5 Wrap the `_pickup_list` read block (the `_task_timestamps.get(a.get("id", ""), {})` lookups inside the list comprehension) with `with _task_timestamps_lock` (snapshot the relevant entries before building the list).

## 2. Lock `_dashboard_port_crew` (transport/server.py)

- [ ] 2.1 Add `_dashboard_port_crew_lock = threading.Lock()` alongside `_dashboard_port_crew` at module level in `transport/server.py`.
- [ ] 2.2 Wrap the `_dashboard_port_crew[dashboard_port] = crew_id` write in `_handle_crew_dashboard_post` with `with _dashboard_port_crew_lock`.
- [ ] 2.3 Wrap the `_dashboard_port_crew.pop(...)` write in `_handle_crew_dashboard_delete` with `with _dashboard_port_crew_lock`.
- [ ] 2.4 Wrap the `_dashboard_port_crew.get(port_int)` and `_dashboard_port_crew.get(int(fwd_port))` reads in `_handle_dashboard_auth` with `with _dashboard_port_crew_lock`.
- [ ] 2.5 Wrap the `_dashboard_port_crew[dashboard_port] = crew_id` write in `launch` (after `_caddy_register_crew`) with `with _dashboard_port_crew_lock`.
- [ ] 2.6 Wrap the `_dashboard_port_crew.pop(int(_ui_p), None)` write in `nuke` with `with _dashboard_port_crew_lock`.
- [ ] 2.7 Wrap the `_dashboard_port_crew[int(_p)] = _cid` writes in `_main` (the startup restore loop) with `with _dashboard_port_crew_lock`.

## 3. Per-crew asyncio lock for `_ensure_crew_running` call sites (transport/server.py)

- [ ] 3.1 Add `_ensure_running_locks: dict[str, asyncio.Lock] = {}` and `_ensure_running_locks_lock = threading.Lock()` at module level in `transport/server.py`.
- [ ] 3.2 Add a helper `_get_ensure_running_lock(crew_id: str) -> asyncio.Lock` that lazily creates and returns a per-crew `asyncio.Lock` from `_ensure_running_locks`, protected by `_ensure_running_locks_lock`.
- [ ] 3.3 In `_handle_crew_ui_proxy`: wrap `await asyncio.to_thread(_ensure_crew_running, crew, crew_id)` with `async with _get_ensure_running_lock(crew_id)`.
- [ ] 3.4 In `_handle_crew_ui_ws_proxy`: wrap `await asyncio.to_thread(_ensure_crew_running, crew, crew_id)` with `async with _get_ensure_running_lock(crew_id)`.
- [ ] 3.5 In `_handle_crew_api_proxy`: wrap `await asyncio.to_thread(_ensure_crew_running, crew, crew_id)` with `async with _get_ensure_running_lock(crew_id)`.

## 4. Unit tests — `_task_timestamps` lock (tests/unit/test_server.py)

- [ ] 4.1 Write a test that dispatches concurrent writes to `_task_timestamps` from multiple threads (via `concurrent.futures.ThreadPoolExecutor`) and asserts all entries are present and no entry is missing or partially overwritten.
- [ ] 4.2 Write a test that interleaves a `dispatch`-style write and a `_pickup_single`-style read-modify-write for the same `task_id` from two threads and asserts `started_at` and `completed_at` are not corrupted.

## 5. Unit tests — `_dashboard_port_crew` lock (tests/unit/test_server.py)

- [ ] 5.1 Write a test that concurrently calls `_handle_crew_dashboard_post` for the same crew from two async tasks and asserts the port-to-crew mapping is consistent (no duplicate ports, no lost entries).
- [ ] 5.2 Write a test that concurrently calls `_handle_dashboard_auth` while a `_handle_crew_dashboard_delete` is in progress and asserts the read either sees the entry or sees it absent — never a partial state.

## 6. Unit tests — per-crew asyncio lock (tests/unit/test_lifecycle.py)

- [ ] 6.1 Write a test that invokes `_ensure_crew_running` concurrently from two async coroutines for the same `crew_id` while the container is stopped and asserts `container_start` is called exactly once.
- [ ] 6.2 Write a test that invokes `_ensure_crew_running` concurrently from two async coroutines for different `crew_id` values and asserts both `container_start` calls proceed without serialisation against each other.

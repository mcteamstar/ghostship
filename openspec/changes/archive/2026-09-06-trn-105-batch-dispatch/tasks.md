## 1. Registry — Batch CRUD

- [x] 1.1 Add `_write_batch(crew_id, batch_id, task_ids, status)` to `transport/registry.py` — writes a batch entry under `crews[crew_id]["batches"]` atomically within `_registry_lock`
- [x] 1.2 Add `_get_batch(crew_id, batch_id)` to `transport/registry.py` — returns the batch entry dict or `None` if not found
- [x] 1.3 Add `_update_batch_status(crew_id, batch_id, status)` to `transport/registry.py` — updates `status` field (`pending` → `partial` → `complete`) atomically
- [x] 1.4 Add `_delete_batch(crew_id, batch_id)` to `transport/registry.py` — removes a single batch entry; used for cleanup
- [x] 1.5 Update `nuke()` in `transport/server.py` to remove the `batches` list from the crew's registry entry as part of the same atomic write that removes the crew — ensures no orphan batch records survive a nuke

## 2. Batch Dispatch — `transport/server.py`

- [x] 2.1 Add `tasks: list[str] | None = None` parameter to the `dispatch` MCP tool signature in `transport/server.py`
- [x] 2.2 Add runtime mutual-exclusion guard: if both `task` and `tasks` are supplied, return `{"error": "Provide either task or tasks, not both"}`; if neither is supplied, return `{"error": "Provide task or tasks"}`
- [x] 2.3 Add size validation for `tasks`: reject an empty list or a list with exactly one item (direct the caller to `task=`), and reject lists exceeding `GA_BATCH_MAX_TASKS` (default 20, read from env)
- [x] 2.4 Implement the batch dispatch loop: iterate `tasks`, call `/api/spawn` for each, collect `task_id` per task; on first `CrewUnresponsiveError` or unexpected failure, break and record partial state
- [x] 2.5 On successful full dispatch, call `_write_batch` with `status="pending"` and return `{"batch_id": ..., "task_ids": [...], "crew_id": ..., "status": "dispatched", "agent": ..., "created_at": ...}`
- [x] 2.6 On partial dispatch failure, call `_write_batch` with `status="partial"`, return the successful `task_ids` so far plus an `error` field, and set `status: "partial"` in the response
- [x] 2.7 Update `dispatch` docstring to document `tasks` parameter, mutual-exclusion note, `batch_id` in response shape, and the `GA_BATCH_MAX_TASKS` cap

## 3. Batch Pickup — `transport/lifecycle.py`

- [x] 3.1 Add `_pickup_batch(crew, crew_id, task_ids, podman, container, timeout_secs)` function to `transport/lifecycle.py` — orchestrates per-round sequential calls to `_pickup_single(timeout_secs=0)` for each task ID
- [x] 3.2 In `_pickup_batch`: handle 404 / missing task responses by marking that task as `{"done": false, "lost": true, "error": "task not found in gateway"}` rather than raising
- [x] 3.3 In `_pickup_batch`: implement the poll loop — sleep 3 s between rounds, respect `GA_PICKUP_MAX_POLL_SECS` cap per total wall time, return with `reason: "timeout"` when the cap fires
- [x] 3.4 In `_pickup_batch`: implement Admiral-mail early-return — read admiral mail count before the first round and return with `reason: "admiral_mail"` if the count increases mid-polling
- [x] 3.5 In `_pickup_batch`: when all tasks are `done`, call `_update_batch_status(crew_id, batch_id, "complete")` if a `batch_id` is known (optional arg), then return with `done: true`

## 4. Batch Pickup — `transport/server.py`

- [x] 4.1 Add `task_ids: list[str] | None = None` parameter to the `pickup` MCP tool signature in `transport/server.py`
- [x] 4.2 Add runtime mutual-exclusion guard on `pickup`: if both `task_id` and `task_ids` are supplied, return `{"error": "Provide either task_id or task_ids, not both"}`
- [x] 4.3 Add empty-list guard: if `task_ids=[]`, return `{"error": "task_ids must not be empty"}`
- [x] 4.4 Route `pickup` to `_pickup_batch` when `task_ids` is provided; pass `timeout_secs` through as-is (the existing `effective_timeout` cap logic already normalises it)
- [x] 4.5 Update `pickup` docstring to document `task_ids` parameter, batch response shape, `reason` field semantics, and lost-member behaviour

## 5. Verification

- [x] 5.1 Write a unit test for `_write_batch` / `_get_batch` / `_update_batch_status` / `_delete_batch` in `tests/` — confirm round-trip read/write and that nuke removes the `batches` key
- [x] 5.2 Write a unit test for the `dispatch` mutual-exclusion guard, size validation, and partial-failure path (mock `_crew_api_with_recovery` to fail on the second call)
- [x] 5.3 Write a unit test for `_pickup_batch` lost-member detection (mock `_pickup_single` to raise for one task ID, assert `lost: true` in output)
- [x] 5.4 Write a unit test for `_pickup_batch` timeout path (mock all tasks as not-done, assert `reason: "timeout"` and `done: false`)
- [x] 5.5 Run `python3 -m py_compile transport/server.py transport/lifecycle.py transport/registry.py` and confirm no syntax errors
- [x] 5.6 Run `openspec status --change trn-105-batch-dispatch` and confirm all artifacts are green / planning complete

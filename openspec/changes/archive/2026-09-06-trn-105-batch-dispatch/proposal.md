## Why

Dispatching N independent tasks today requires N serial `dispatch` calls followed by N separate `pickup` polls, creating quadratic round-trip overhead for callers and making fan-out workflows fragile when the caller dies mid-loop. KiroCrew's own `spawn_run` (batch identity) and `spawn_sub_agents` (blocking variant in 0.5.0) prove the pattern is sound — ghostship should expose the same primitive natively so MCP callers can hand off parallel work atomically and block until all results are ready.

## What Changes

- **`dispatch` gains an optional `tasks: list[str]` parameter.** When provided, all tasks are dispatched atomically against the same crew and the tool returns a `batch_id` and per-task `task_id` list. The existing `task: str` path is unchanged; callers may use either but not both. **BREAKING** in schema only: MCP schema emits both `task` and `tasks` parameters; existing `task` callers are unaffected.
- **`pickup` gains a `task_ids: list[str]` parameter.** When provided together with a non-zero `timeout_secs`, the call blocks until every listed task is done (or the timeout fires), then returns per-task results in one response. The existing single-`task_id` path is unchanged.
- **`batch_id` stored in the transport registry** (`crews.json` under the relevant crew). Each batch entry records its `batch_id`, constituent `task_ids`, `created_at`, and `status` (`pending | partial | complete`). This enables lost-member detection: if the crew dies mid-batch, a subsequent `pickup(batch_id=...)` or `pickup(task_ids=[...])` can report which tasks have no recorded start — they were lost before `/api/spawn` reached the gateway.
- **New `_pickup_batch` helper in `transport/lifecycle.py`** — parallel polling across N task IDs using the existing `_pickup_single` building blocks; respects the existing `GA_PICKUP_MAX_POLL_SECS` cap per cycle.
- **`transport/registry.py`** gains batch CRUD: `_write_batch`, `_get_batch`, `_delete_batch`, `_update_batch_status`.

## Capabilities

### New Capabilities

- `batch-dispatch`: Atomic multi-task dispatch and blocking multi-task pickup. Covers the `dispatch(tasks=[...])` MCP tool overload, the `batch_id` registry record, the `pickup(task_ids=[...], timeout_secs=N)` blocking batch pickup path, and lost-member detection semantics.

### Modified Capabilities

- `task-orchestration`: Requirements for `dispatch` (new `tasks` parameter, batch return shape) and `pickup` (new `task_ids` parameter, batch result shape) are spec-level behavior changes that extend the existing scenarios in this spec.

## Impact

- `transport/server.py` — `dispatch` and `pickup` MCP tool signatures and dispatch logic
- `transport/lifecycle.py` — new `_pickup_batch` function; `_pickup_single` called as subroutine
- `transport/registry.py` — new batch CRUD helpers; `crews.json` schema gains per-crew `batches` list
- No new external dependencies; no changes to crew containers, gateway API, or client auth

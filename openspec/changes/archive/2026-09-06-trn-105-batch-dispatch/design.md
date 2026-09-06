## Context

See `proposal.md — Why` for motivation.

The current dispatch/pickup surface is single-task only: `dispatch(task=str)` → one `task_id`; `pickup(task_id=str)` → one result. The underlying machinery is already capable — every task is a KiroCrew subagent, `/api/spawn` handles each one independently, and `_pickup_single` in `lifecycle.py` already does the poll/timeout loop for one task. Batch support is a fan-out layer built on top of the existing primitives, not a rewrite of them.

Key existing constraints that shape the design:

- `GA_PICKUP_MAX_POLL_SECS` (default 30 s): transport hard-caps a single poll window. Batch pickup must respect this per round.
- `/api/spawn` is not a batch endpoint on the gateway side. Each task in a batch requires its own POST. Sequential dispatch is safe; parallel dispatch could saturate the gateway.
- `crews.json` is the single-writer registry (guarded by `_registry_lock`). Batch records live there per-crew to stay co-located with schedule and crew metadata.
- `_pickup_single` is synchronous and blocks its thread. Multiple concurrent calls per batch round would require threads; sequential calls are simpler and sufficient given the poll-window model.

---

## Goals / Non-Goals

**Goals:**
- Atomic N-task dispatch with a single `batch_id` identifier and per-task `task_ids` in one response
- Lost-member detection: identify which tasks in a batch never started if the crew dies mid-dispatch
- Blocking batch pickup: one `pickup(task_ids=[...], timeout_secs=N)` call collects all results
- Backward compatibility: existing `dispatch(task=...)` and `pickup(task_id=...)` callers are untouched

**Non-Goals:**
- Gateway-side batch spawn endpoint (would require crew container changes — out of scope)
- True parallel polling within one round (sequential is sufficient; parallel complicates error handling)
- Heterogeneous agents per batch (all tasks in a batch share one `agent`)
- Batch `steer` or batch `nuke`

---

## Decisions

### D1 — `tasks: list[str]` overload on the existing `dispatch` tool, not a separate `batch_dispatch` tool

**Decision:** Add `tasks` as an optional alternative parameter on `dispatch`, mutually exclusive with `task`.

**Rationale:** The batch path shares all validation logic (agent allowlist, model validation, crew lookup, `_ensure_crew_running`). A separate tool would duplicate that validation, add a second MCP surface to document, and split the mental model. One tool with two modes (single vs. batch) keeps the schema surface minimal. The MCP JSON schema emits both `task` and `tasks` as optional parameters with a mutual-exclusion note in the docstring; MCP does not support `oneOf` natively, so the exclusion is enforced at runtime.

**Alternative considered:** Separate `batch_dispatch` tool. Rejected: doubles MCP surface area with no caller benefit; all dispatch logic is shared.

### D2 — `batch_id` persisted in `crews.json`, not returned ephemerally only

**Decision:** Write a batch record to `crews.json` under `crews[crew_id]["batches"]` at dispatch time.

**Rationale:** An ephemeral-only `batch_id` (returned but not stored) provides no lost-member detection — if the transport restarts between dispatch and pickup, the caller has no way to know which tasks were actually started. Storing the batch record with per-task IDs lets any subsequent pickup call identify tasks that appear in the batch record but have no gateway entry (lost members). The registry is already the authoritative source of truth for schedule and crew state; batch records fit naturally.

**Alternative considered:** Ephemeral only — return `batch_id` + `task_ids` and rely on the caller to track them. Rejected: defeats lost-member detection, which is a stated goal.

**Registry schema addition (per-crew):**
```json
"batches": [
  {
    "batch_id": "<uuid>",
    "task_ids": ["<id1>", "<id2>"],
    "created_at": "<iso8601>",
    "status": "pending | partial | complete"
  }
]
```

### D3 — Sequential `/api/spawn` calls within a batch dispatch, not parallel

**Decision:** Dispatch each task in the `tasks` list sequentially inside `dispatch()`.

**Rationale:** The gateway's `/api/spawn` endpoint is single-task. Parallel HTTP requests from N threads risk gateway saturation and complicate partial-failure accounting. Sequential dispatch is predictable: tasks are started in list order, and the first failure ends the loop, recording what was started before the failure. Round-trip cost is N × ~50 ms for typical batch sizes (2–20); acceptable since `dispatch` is not a hot path.

**Alternative considered:** Spawn one thread per task and issue concurrent POSTs. Rejected: threading complexity, harder partial-failure bookkeeping, no latency requirement that demands it.

### D4 — Sequential per-round polling in `_pickup_batch`, respecting `GA_PICKUP_MAX_POLL_SECS` per round

**Decision:** `_pickup_batch` polls tasks sequentially within each round (calls `_pickup_single` with `timeout_secs=0` per task, collects results, sleeps, repeats). A round that exhausts `GA_PICKUP_MAX_POLL_SECS` returns with `reason: "timeout"` for the caller to re-poll.

**Rationale:** The existing `_pickup_single(timeout_secs=0)` path is one HTTP GET — cheap. Polling N tasks sequentially per round adds N × ~50 ms per round, negligible for batch sizes up to 20. This reuses the existing capped-poll contract exactly: the caller sees the same `reason: "timeout"` shape and can re-call `pickup(task_ids=[...], timeout_secs=N)` to continue waiting. No new timeout semantics, no new threading model.

**Alternative considered:** A new gateway primitive (e.g., `POST /api/spawn/batch-status`) returning status for N tasks in one call. Rejected: requires crew container changes, breaks the transport-only scope constraint, and adds protocol surface for marginal latency gain.

### D5 — Lost members reported per-task in the batch pickup response, not as a top-level error

**Decision:** When a task ID in `task_ids` returns 404 from the gateway, mark that task as `{"done": false, "lost": true, ...}` in the per-task result map. The overall batch result is still returned; `done: false` at the top level when any member is lost.

**Rationale:** A batch pickup should be maximally informative. Raising a top-level error on a single lost task discards the results of the other N-1 tasks that succeeded. Per-task lost flags let the caller salvage partial results and understand exactly which members failed.

---

## Risks / Trade-offs

**[Risk] Sequential dispatch means a large batch (e.g., 20 tasks) takes ~1 s to dispatch** → Acceptable: dispatch is not latency-sensitive; callers wanting sub-second fan-out can still call `dispatch` N times themselves. The cap `GA_BATCH_MAX_TASKS=20` limits worst-case dispatch time.

**[Risk] Mid-batch crew failure leaves partial batch_id with some task_ids missing** → Mitigated by D2: the registry records which tasks were started before the failure. Lost-member detection in D5 surfaces the gap on the next pickup.

**[Risk] `crews.json` grows unboundedly if batches are never cleaned up** → Batch records should be pruned when a crew is nuked (existing nuke path atomically removes all crew state). An explicit batch status update to `complete` when all members are done also allows a future compaction pass. No compaction task is in scope for this change.

**[Risk] MCP schema cannot enforce `task` / `tasks` mutual exclusion natively** → Enforced at runtime with a clear error message. Documented in the tool docstring. Existing callers always pass `task=`; new callers learn about `tasks=` from the schema. No silent conflict possible.

---

## Migration Plan

This change is fully additive and backward-compatible:

- Existing `dispatch(task=...)` callers: unaffected — the `tasks` parameter is optional and defaults to `None`.
- Existing `pickup(task_id=...)` callers: unaffected — the `task_ids` parameter is optional and defaults to `None`.
- `crews.json` schema: the `batches` field is added lazily (only when a batch dispatch occurs); old crews without it are valid.
- No container image changes, no gateway API changes, no client auth changes.
- Rollback: revert the transport commit. `crews.json` entries with `batches` keys are harmless if the reading code is reverted (unknown keys are ignored by the existing registry loader).

---

## Open Questions

None. All design decisions above are resolved sufficiently to write specs and implement.

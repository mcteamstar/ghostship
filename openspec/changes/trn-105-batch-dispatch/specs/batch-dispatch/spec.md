# Batch Dispatch Specification

## Purpose

Define the contract for atomic multi-task dispatch and blocking multi-task pickup in the ghostship MCP transport. A caller can hand off N independent tasks in a single tool call and block until all results are collected, without managing N round-trips themselves.

## Requirements

### Requirement: Batch dispatch returns a batch_id and per-task IDs

The system SHALL accept `tasks: list[str]` as an alternative to `task: str` on the `dispatch` tool. When `tasks` is provided, the system SHALL dispatch each task sequentially against the named `crew_id`, collect the resulting `task_id` per task, record the batch in the transport registry, and return a `batch_id` and `task_ids` list. The `task` and `tasks` parameters SHALL be mutually exclusive; the system SHALL return an error if both are supplied. The minimum batch size SHALL be 2; the maximum SHALL be capped by `GA_BATCH_MAX_TASKS` (default 20). Each task in the batch uses the same `agent` and optional `model` override as a single-task dispatch.

#### Scenario: Batch dispatch — all tasks start

- **WHEN** `dispatch` is called with `tasks=["task A", "task B", "task C"]`, a valid `crew_id`, and valid `agent`
- **THEN** the system dispatches each task to `/api/spawn`, records a batch entry with `batch_id`, `task_ids`, `status: "pending"`, and `created_at`, and returns `{"batch_id": "<id>", "task_ids": ["<id1>", "<id2>", "<id3>"], "crew_id": "<crew_id>", "status": "dispatched", "agent": "<agent>", "created_at": "<ts>"}`

#### Scenario: Batch dispatch — crew dies mid-batch

- **WHEN** `dispatch` is called with `tasks=[...]` and the crew container becomes unreachable after some but not all `/api/spawn` calls have returned
- **THEN** the system records a `partial` batch entry for the tasks that succeeded and returns a partial result with `status: "partial"`, the `task_ids` that were assigned, and an `error` field naming the failure point — the tasks that never received a `task_id` are the lost members

#### Scenario: Batch dispatch — task and tasks both supplied

- **WHEN** `dispatch` is called with both `task` and `tasks` supplied
- **THEN** the system returns `{"error": "Provide either task or tasks, not both"}`

#### Scenario: Batch dispatch — tasks list too small

- **WHEN** `dispatch` is called with `tasks` containing exactly one item
- **THEN** the system returns `{"error": "tasks must contain at least 2 items; use task= for a single dispatch"}`

#### Scenario: Batch dispatch — tasks list too large

- **WHEN** `dispatch` is called with `tasks` containing more than `GA_BATCH_MAX_TASKS` items
- **THEN** the system returns `{"error": "tasks exceeds maximum batch size of <GA_BATCH_MAX_TASKS>"}`

#### Scenario: Batch dispatch — invalid agent

- **WHEN** `dispatch` is called with `tasks=[...]` and an agent name outside the six-persona roster
- **THEN** the system returns a validation error without dispatching any task

### Requirement: Batch registry record tracks member status

The transport registry SHALL maintain a `batches` list per crew entry in `crews.json`. Each batch entry SHALL include `batch_id` (UUID), `task_ids` (list of string), `created_at` (ISO 8601 UTC), and `status` (`pending` | `partial` | `complete`). When all batch tasks complete, the batch status SHALL be updated to `complete`. Batch records SHALL be removed atomically when the associated crew is nuked.

#### Scenario: Batch record written at dispatch time

- **WHEN** a batch dispatch completes (all or partial)
- **THEN** a batch entry is written to `crews.json` under `crews[crew_id]["batches"]` with the fields listed above

#### Scenario: Batch record removed on nuke

- **WHEN** `nuke(confirm=True)` is called for a crew
- **THEN** the crew's `batches` list is removed as part of the same atomic registry write that removes the crew entry

### Requirement: Blocking batch pickup collects results for a task_ids list

The system SHALL accept `task_ids: list[str]` as an alternative to `task_id: str` on the `pickup` tool. When `task_ids` is provided with `timeout_secs > 0`, the system SHALL poll all listed tasks concurrently (using sequential calls to `_pickup_single` per round) until every task is `done`, the timeout elapses, or new Admiral mail arrives. The response SHALL be a dict keyed by `task_id` with each task's result as the value. When `timeout_secs == 0` and `task_ids` is provided, the system SHALL return a snapshot of each task's current state without blocking. The `task_id` and `task_ids` parameters SHALL be mutually exclusive.

#### Scenario: Blocking batch pickup — all tasks complete before timeout

- **WHEN** `pickup` is called with `task_ids=["id1", "id2"]`, `crew_id`, and `timeout_secs=300`, and both tasks complete before the timeout
- **THEN** the system returns `{"id1": {<full single-task pickup shape>}, "id2": {<full single-task pickup shape>}, "done": true, "completed_tasks": 2, "total_tasks": 2}`

#### Scenario: Blocking batch pickup — timeout fires before all tasks complete

- **WHEN** `pickup` is called with `task_ids=[...]`, `crew_id`, and `timeout_secs=N`, and at least one task is not done when the poll window ends
- **THEN** the system returns the collected results for all tasks (done and not-done) with `"reason": "timeout"`, `"done": false`, and per-task `done` flags in each task result

#### Scenario: Blocking batch pickup — Admiral mail early-return

- **WHEN** `pickup` is called with `task_ids=[...]` and `timeout_secs > 0`, and new Admiral mail arrives while polling
- **THEN** the system returns early with current per-task state and `"reason": "admiral_mail"`

#### Scenario: Blocking batch pickup — timeout_secs == 0 returns snapshot

- **WHEN** `pickup` is called with `task_ids=[...]` and `timeout_secs=0` (default)
- **THEN** the system queries each task once and returns their current states without blocking — no `reason` field is included unless a task individually has one

#### Scenario: task_id and task_ids both supplied

- **WHEN** `pickup` is called with both `task_id` and `task_ids` set
- **THEN** the system returns `{"error": "Provide either task_id or task_ids, not both"}`

#### Scenario: Batch pickup with empty task_ids list

- **WHEN** `pickup` is called with `task_ids=[]`
- **THEN** the system returns `{"error": "task_ids must not be empty"}`

### Requirement: Lost-member detection

When `pickup` is called with `task_ids` and one or more of the listed IDs has no record in the gateway (i.e. `/api/spawn/<id>` returns 404), the system SHALL mark that task as `lost` in the response rather than raising an error for the whole batch. A `lost` task result SHALL include `{"task_id": "<id>", "done": false, "lost": true, "error": "task not found in gateway"}`. The overall batch result SHALL still be returned; the `done` field for the batch SHALL be `false` when any member is lost.

#### Scenario: One task lost mid-batch

- **WHEN** `pickup` is called with `task_ids=["id1", "id2"]` and `id2` returns 404 from the gateway
- **THEN** the response includes a normal result for `id1` and `{"task_id": "id2", "done": false, "lost": true, "error": "task not found in gateway"}` for `id2`, and the overall `done: false`

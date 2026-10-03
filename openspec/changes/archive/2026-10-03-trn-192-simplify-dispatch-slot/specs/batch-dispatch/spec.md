## MODIFIED Requirements

### Requirement: Batch dispatch returns a batch_id and per-task IDs

The system SHALL accept `tasks: list[str]` as an alternative to `task: str` on
the `dispatch` tool. When `tasks` is provided, the system SHALL dispatch each
task sequentially against the named `crew_id`, collect the resulting `task_id`
per task, record the batch in the transport registry, and return a `batch_id`
and `task_ids` list. The `task` and `tasks` parameters SHALL be mutually
exclusive; the system SHALL return an error if both are supplied. The minimum
batch size SHALL be 2; the maximum SHALL be capped by `GA_BATCH_MAX_TASKS`
(default 20). Each task in the batch uses the same `agent`, optional `model`
override, and `slot` (either `None` or `False`) as a single-task dispatch. The
response SHALL NOT include a `task_slots` field; per-task UUID slot names are
not generated for batch dispatch.

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

## REMOVED Requirements

### Requirement: Per-task UUID slot generation in batch dispatch

**Reason**: `slot=True` UUID auto-generation is removed from the slot model.
The `task_slots` response field was only emitted when `slot=True` was used for
batch dispatch. With UUID slots removed, the per-task slot map has no purpose.

**Migration**: Batch callers that used `slot=True` to obtain isolated per-task
sessions should omit `slot` (or pass `slot=None`), which routes enrolled agents
to their shared member DM slot. For headless batch dispatch, pass `slot=False`.
The `task_slots` field will no longer appear in batch dispatch responses.

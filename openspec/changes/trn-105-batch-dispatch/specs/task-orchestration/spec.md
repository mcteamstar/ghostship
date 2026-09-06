# Task Orchestration — Batch Dispatch Delta Spec

## Purpose (delta)

Extend the task orchestration spec to cover the new `tasks` parameter on `dispatch` and the new `task_ids` parameter on `pickup`. All existing requirements in `openspec/specs/task-orchestration/spec.md` remain in force; this file adds only the batch-path requirements.

## ADDED Requirements

### Requirement: dispatch accepts tasks list as an alternative overload

The `dispatch` tool SHALL accept `tasks: list[str]` as an alternative to `task: str`. The two parameters SHALL be mutually exclusive. When `tasks` is provided, all dispatch semantics (agent validation, model validation, crew lookup, `_ensure_crew_running`) apply identically to each task in the list before any `/api/spawn` call is made. All tasks in one batch share the same `agent`, `model`, and `crew_id`.

See `specs/batch-dispatch/spec.md` for the full batch dispatch contract, registry record, and error scenarios.

#### Scenario: Batch dispatch uses same validation as single dispatch

- **WHEN** `dispatch` is called with `tasks=[...]` and an agent not on the six-persona roster
- **THEN** the system returns a validation error without dispatching any task — identical behaviour to `dispatch(task=..., agent="invalid")`

#### Scenario: Batch dispatch records last_task_at per task

- **WHEN** `dispatch` is called with `tasks=[...]` and all `/api/spawn` calls succeed
- **THEN** the transport updates `last_task_at` in the crew registry for each successfully dispatched task, using the timestamp of that task's `/api/spawn` response

### Requirement: pickup accepts task_ids list for batch collection

The `pickup` tool SHALL accept `task_ids: list[str]` as an alternative to `task_id: str`. The two parameters SHALL be mutually exclusive. When `task_ids` is provided, the tool routes to `_pickup_batch` in `lifecycle.py`, which polls each task ID sequentially per round and aggregates results. The existing `GA_PICKUP_MAX_POLL_SECS` cap applies per round across all members.

See `specs/batch-dispatch/spec.md` for the full blocking batch pickup contract and lost-member semantics.

#### Scenario: pickup(task_ids=...) inherits the existing timeout cap

- **WHEN** `pickup` is called with `task_ids=[...]` and `timeout_secs` greater than `GA_PICKUP_MAX_POLL_SECS`
- **THEN** each polling round completes within `GA_PICKUP_MAX_POLL_SECS`, the system returns with `"reason": "timeout"`, and the caller may re-poll to continue waiting — identical to the single-task `pickup` internal-cap behaviour

#### Scenario: pickup(task_ids=...) without crew_id returns an error

- **WHEN** `pickup` is called with `task_ids=[...]` and no `crew_id`
- **THEN** the system returns `{"error": "crew_id is required"}` — same behaviour as single-task pickup without crew_id

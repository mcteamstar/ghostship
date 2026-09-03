# task-timestamps Specification

## Purpose

Expose wall-clock timestamps for task lifecycle events in `dispatch` and `pickup` responses, giving the Admiral a reliable time anchor when tracking work across crews.

## Requirements

### Requirement: dispatch response includes created_at

The `dispatch` tool SHALL include a `created_at` field in its response, containing the ISO 8601 UTC timestamp at which the task was registered.

#### Scenario: dispatch returns created_at
- **WHEN** `dispatch` is called and the task is accepted
- **THEN** the response includes `created_at` as an ISO 8601 UTC string (e.g. `"2026-09-01T13:05:00Z"`)

### Requirement: pickup (task) response includes lifecycle timestamps

The `pickup` tool, when called with a `task_id`, SHALL include `created_at`, `started_at`, and `completed_at` fields in its response.

- `created_at`: when the task was dispatched. Always present.
- `started_at`: when the agent began executing. Present once the task has started; `null` if not yet started.
- `completed_at`: when the task finished (done or error). Present once complete; `null` if still running.

#### Scenario: pickup on a running task
- **WHEN** `pickup` is called with a `task_id` for a task that is still running
- **THEN** the response includes `created_at` and `started_at` as ISO 8601 strings, and `completed_at` is `null`

#### Scenario: pickup on a completed task
- **WHEN** `pickup` is called with a `task_id` for a completed task
- **THEN** the response includes `created_at`, `started_at`, and `completed_at` as ISO 8601 strings

### Requirement: pickup (crew-wide) task list entries include timestamps

When `pickup` is called without a `task_id`, each task entry in the returned list SHALL include `created_at`, `started_at`, and `completed_at` with the same semantics as above.

#### Scenario: crew-wide pickup includes timestamps per task
- **WHEN** `pickup` is called with only `crew_id`
- **THEN** each task object in the list includes `created_at`, `started_at`, and `completed_at`

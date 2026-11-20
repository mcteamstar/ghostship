# task-timestamps Specification

## Purpose

Expose wall-clock timestamps for task lifecycle events in `dispatch` and `pickup` responses, giving the Admiral a reliable time anchor when tracking work across crews.

## Requirements

### Requirement: dispatch response includes created_at
The `dispatch` tool SHALL include a `created_at` field in its response, containing the ISO 8601 UTC timestamp at which the task was registered. Writes to the in-memory timestamp store SHALL be protected by a `threading.Lock` so that concurrent `dispatch` calls from multiple threads do not race on the shared dict.

#### Scenario: dispatch returns created_at
- **WHEN** `dispatch` is called and the task is accepted
- **THEN** the response includes `created_at` as an ISO 8601 UTC string (e.g. `"2026-09-01T13:05:00Z"`)

#### Scenario: Concurrent dispatch calls do not corrupt timestamp store
- **WHEN** multiple `dispatch` calls execute concurrently from different threads
- **THEN** each task's `created_at` entry is written atomically and no entry is lost or partially overwritten

### Requirement: pickup (task) response includes lifecycle timestamps

`pickup(task_id=...)` SHALL return `created_at`, `started_at`, and `completed_at`; creation time is always present, while the latter fields are null until the task starts or completes.

#### Scenario: pickup on a running task
- **WHEN** `pickup` is called with a `task_id` for a task that is still running
- **THEN** the response includes `created_at` and `started_at` as ISO 8601 strings, and `completed_at` is `null`

#### Scenario: pickup on a completed task
- **WHEN** `pickup` is called with a `task_id` for a completed task
- **THEN** the response includes `created_at`, `started_at`, and `completed_at` as ISO 8601 strings

### Requirement: Task timestamps are synchronized

Reads and conditional timestamp updates in `pickup` SHALL use the same `threading.Lock` as `dispatch`.

#### Scenario: Concurrent pickup and dispatch on the same task
- **WHEN** a `pickup` call reads and updates timestamps concurrently with a `dispatch` call writing to the same store
- **THEN** no timestamp entry is lost or partially written
### Requirement: pickup (crew-wide) task list entries include timestamps
When `pickup` is called without a `task_id`, each task entry in the returned list SHALL include `created_at`, `started_at`, and `completed_at` with the same semantics as above. The read of the timestamp store for the crew-wide list SHALL also be protected by the `threading.Lock`.

#### Scenario: crew-wide pickup includes timestamps per task
- **WHEN** `pickup` is called with only `crew_id`
- **THEN** each task object in the list includes `created_at`, `started_at`, and `completed_at`

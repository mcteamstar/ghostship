# task-orchestration/timestamps Specification

## Purpose

Defines how Transport records and exposes task timing.

## Requirements

### Requirement: Bounded in-process memory for task timestamp tracking

On each `_pickup_single` and `_pickup_list`, transport SHALL evict completed `_task_timestamps` entries older than `_TASK_TIMESTAMP_TTL_SECS` (default 3600s), under its lock after updating current timestamps. It SHALL scan only completed entries. `GA_TASK_TIMESTAMP_TTL_SECS` SHOULD configure the TTL.

#### Scenario: Completed task entries are evicted after TTL

- **GIVEN** a transport process that has dispatched many tasks over several hours
- **WHEN** `_pickup_single` or `_pickup_list` is called for a task
- **THEN** any entries in `_task_timestamps` whose `completed_at` is more than `_TASK_TIMESTAMP_TTL_SECS` seconds in the past are removed from the map before the call returns

#### Scenario: Active task entries are not evicted

- **GIVEN** a task that is still running (no `completed_at`)
- **WHEN** eviction runs
- **THEN** that task's timestamp entry is retained

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

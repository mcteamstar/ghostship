## MODIFIED Requirements

### Requirement: Schedule tool supports cancel action

The `schedule` tool SHALL accept an `action` parameter with value `"cancel"` and a required `job_id` parameter. When invoked, it SHALL remove the identified job from the crew's cron registry. The tool SHALL return `{"status": "cancelled", "job_id": "<id>"}` on success, or `{"error": "<reason>"}` if the job does not exist or cannot be cancelled.

#### Scenario: Cancel an existing job

- **WHEN** the Admiral calls `schedule(action="cancel", job_id="abc123", crew_id="my-crew")`
- **THEN** the job with id `abc123` is removed from the crew's cron registry and the tool returns `{"status": "cancelled", "job_id": "abc123"}`

#### Scenario: Cancel a non-existent job

- **WHEN** the Admiral calls `schedule(action="cancel", job_id="nonexistent", crew_id="my-crew")`
- **THEN** the tool returns `{"error": "Job not found: nonexistent"}`

### Requirement: Schedule tool supports list action

The `schedule` tool SHALL accept an `action` parameter with value `"list"`. When invoked, it SHALL return all active scheduled jobs for the specified crew. Each job entry SHALL include `job_id`, `name`, `schedule`, `agent`, `enabled`, and `last_run` fields.

#### Scenario: List jobs on a crew with active jobs

- **WHEN** the Admiral calls `schedule(action="list", crew_id="my-crew")` and the crew has two scheduled jobs
- **THEN** the tool returns `{"jobs": [{"job_id": "...", "name": "...", "schedule": "...", "agent": "...", "enabled": true, "last_run": "..."}, ...]}` with one entry per active job

#### Scenario: List jobs on a crew with no jobs

- **WHEN** the Admiral calls `schedule(action="list", crew_id="my-crew")` and the crew has no scheduled jobs
- **THEN** the tool returns `{"jobs": []}`

### Requirement: Dispatch tool supports fire_after_secs parameter

The `dispatch` tool SHALL accept an optional `fire_after_secs` integer parameter. When provided, the task SHALL NOT be dispatched immediately but SHALL be scheduled as a one-shot job that fires once after the specified number of seconds. The minimum value SHALL be 1. The tool SHALL return the scheduled `job_id` along with `status: "delayed"` and the `fire_after_secs` value.

#### Scenario: Dispatch with delay

- **WHEN** the Admiral calls `dispatch(task="run cleanup", agent="ghost", crew_id="my-crew", fire_after_secs=300)`
- **THEN** the task is not dispatched immediately, a one-shot cron job is created to fire in 300 seconds, and the tool returns `{"task_id": null, "job_id": "<id>", "crew_id": "my-crew", "status": "delayed", "fire_after_secs": 300, "agent": "ghost"}`

#### Scenario: Dispatch with invalid delay

- **WHEN** the Admiral calls `dispatch(task="run cleanup", crew_id="my-crew", fire_after_secs=0)`
- **THEN** the tool returns `{"error": "fire_after_secs must be >= 1"}`

## ADDED Requirements

### Requirement: transport://jobs resource exposes scheduled jobs

The transport server SHALL expose a `transport://jobs` MCP resource that returns the list of all scheduled jobs across all running crews. Each job entry SHALL include `job_id`, `crew_id`, `name`, `schedule`, `agent`, `enabled`, `last_run`, and `last_status` fields. The resource SHALL be readable by any MCP client connected to the transport.

#### Scenario: Read jobs resource with active crews

- **WHEN** an MCP client reads `transport://jobs` and there are two crews with a total of three scheduled jobs
- **THEN** the resource returns a plain-text formatted listing of all three jobs grouped by crew, including each job's id, name, schedule expression, agent, enabled state, and last run timestamp

#### Scenario: Read jobs resource with no running crews

- **WHEN** an MCP client reads `transport://jobs` and no crews are running
- **THEN** the resource returns `"No running crews found."` or an empty listing

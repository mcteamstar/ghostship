# task-orchestration/scheduling Specification

## Purpose

Defines recurring and delayed tasks, schedule lifecycle and runtime reconciliation.

## Requirements

### Requirement: Gateway cron state is reconciled after restart

Once ready, the transport SHALL read `/api/crons`, update registry state for jobs present in the gateway, and reseed only jobs absent there; the gateway is the source of truth.

#### Scenario: Paused cron in gateway syncs to registry on restart
- **WHEN** a crew container restarts and its gateway reports a cron job with `"enabled": false`
- **THEN** the transport updates the registry entry for that job to `enabled: false`, does not re-register it, and the idle monitor subsequently sees no enabled cron job for that crew

#### Scenario: Missing cron registered from registry on restart
- **WHEN** a crew container restarts and a registry schedule entry is absent from the gateway's `/api/crons` response
- **THEN** the transport registers it in the gateway (the true bootstrap case — brand new container)

### Requirement: Schedule monitor uses gateway enabled state

When reachable, the schedule monitor SHALL read `/api/crons` for enabled status, skip disabled jobs, and write `enabled: false` back to the registry.

#### Scenario: Gateway reports job disabled — monitor skips and writes back

- **WHEN** the schedule monitor evaluates a due job and the gateway's `/api/crons` response for that crew lists the job with `"enabled": false`
- **THEN** the monitor does not fire the job, and writes `enabled: false` to the registry entry for that job

#### Scenario: Gateway reports job enabled — monitor fires normally

- **WHEN** the schedule monitor evaluates a due job and the gateway's `/api/crons` response for that crew lists the job with `"enabled": true`
- **THEN** the monitor fires the job as normal (existing behaviour)

### Requirement: Schedule monitor falls back to registry when gateway is unreachable

For a stopped crew that cannot be woken, the monitor SHALL use registry `enabled` as a best-effort fallback; a missing gateway field SHALL default to enabled.

#### Scenario: Crew stopped, gateway unreachable — monitor falls back to registry

- **WHEN** the schedule monitor evaluates a job for a crew that cannot be woken (`_ensure_crew_running` raises or the crew was already stopped before the gateway fetch), so the gateway's `/api/crons` response is unavailable
- **THEN** the monitor falls back to the registry's `enabled` field to decide whether to skip; if the registry shows `enabled: false` the job is skipped; if the registry shows `enabled: true` (or the field is absent) the job proceeds with the existing wake-and-fire path

#### Scenario: Gateway cron payload field is absent — monitor treats job as enabled

- **WHEN** the gateway's `/api/crons` response includes a job entry but the `"enabled"` field is absent
- **THEN** the monitor treats the job as enabled and fires it (fail-open, preserving existing behaviour)

### Requirement: Recurring task scheduling
The system SHALL schedule by either cron or `interval` seconds and reject requests supplying both or neither. It SHALL default `agent` to `ghost`; Raven check-ins SHALL name Raven explicitly. `fire_immediately` SHALL control whether a task runs once at creation before the first scheduled tick.

#### Scenario: Schedule by cron
- **WHEN** `schedule` is called with a `cron` expression and no `interval`
- **THEN** the system creates a cron job on the crew with the given timezone and returns a `job_id`

#### Scenario: Schedule by interval
- **WHEN** `schedule` is called with `interval` (in seconds) and no `cron`
- **THEN** the system creates an interval job on the crew and returns a `job_id`

#### Scenario: Both or neither provided
- **WHEN** `schedule` is called with both `cron` and `interval`, or with neither
- **THEN** the system returns an error and creates no job

#### Scenario: Default agent for a scheduled job
- **WHEN** `schedule` is called without an explicit `agent`
- **THEN** the job dispatches `ghost`, matching `dispatch`'s default rather than selecting a Captain-specific persona

#### Scenario: fire_immediately defaults to true for interval jobs
- **WHEN** `schedule` is called with `interval` set and `fire_immediately` not specified
- **THEN** the system defaults `fire_immediately` to `true` and dispatches the job's task once immediately after creating the cron job

#### Scenario: fire_immediately defaults to false for cron jobs
- **WHEN** `schedule` is called with `cron` set and `fire_immediately` not specified
- **THEN** the system defaults `fire_immediately` to `false` and does not dispatch immediately

#### Scenario: Immediate dispatch does not affect the schedule
- **WHEN** `schedule` is called with `fire_immediately` true and `interval` set to N seconds
- **THEN** the immediate dispatch occurs at creation time, and the next scheduled dispatch occurs at `created_at + N` seconds — the immediate run does not shift or reset the interval timer

#### Scenario: every_secs parameter is rejected
- **WHEN** `schedule` is called with `every_secs` as the parameter name
- **THEN** the system returns a validation error indicating the parameter has been renamed to `interval`

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

### Requirement: transport://jobs resource exposes scheduled jobs

The transport server SHALL expose a `transport://jobs` MCP resource that returns the list of all scheduled jobs across all running crews. Each job entry SHALL include `job_id`, `crew_id`, `name`, `schedule`, `agent`, `enabled`, `last_run`, and `last_status` fields. The resource SHALL be readable by any MCP client connected to the transport.

#### Scenario: Read jobs resource with active crews

- **WHEN** an MCP client reads `transport://jobs` and there are two crews with a total of three scheduled jobs
- **THEN** the resource returns a plain-text formatted listing of all three jobs grouped by crew, including each job's id, name, schedule expression, agent, enabled state, and last run timestamp

#### Scenario: Read jobs resource with no running crews

- **WHEN** an MCP client reads `transport://jobs` and no crews are running
- **THEN** the resource returns `"No running crews found."` or an empty listing

### Requirement: Transport maintains authoritative schedule registry

The transport SHALL maintain a `schedules` list per crew entry in `crews.json`.
Each entry SHALL include `job_id`, `name`, `interval_secs`, `cron_expr`,
`next_fire_at`, `agent`, and `message`. Writes to the schedule SHALL go to both
the transport registry and the gateway cron API. On divergence, the transport
registry is the source of truth.

#### Scenario: Captain order persists schedule in registry
- **WHEN** `captain(action="order", ...)` creates a new check-in job
- **THEN** the job is written to the gateway cron API AND stored in the transport registry under that crew's `schedules` list

#### Scenario: schedule(action="cancel") removes from registry
- **WHEN** `schedule(action="cancel", job_id=..., crew_id=...)` is called
- **THEN** the job is removed from the gateway cron API AND removed from the transport registry

#### Scenario: schedule(action="list") reads from registry when crew stopped
- **WHEN** `schedule(action="list", crew_id=...)` is called AND the crew is stopped
- **THEN** the tool returns the schedule from the transport registry without attempting to contact the gateway

### Requirement: Transport wakes idle crews before scheduled ticks fire

The transport SHALL run a background `_schedule_monitor` loop that checks for
due jobs every 30 seconds. When a job is due and its crew is stopped, the
transport SHALL call `_ensure_crew_running` before the tick fires. If the crew
cannot be started within the timeout, the transport SHALL skip the tick and
reschedule it for the next interval.

#### Scenario: Captain tick fires on idle crew
- **WHEN** a captain check-in is due AND the crew container is stopped
- **THEN** the transport starts the crew, waits for the gateway to be ready, then fires the tick via the gateway REST API

#### Scenario: Crew cannot be started
- **WHEN** a tick is due AND `_ensure_crew_running` fails
- **THEN** the tick is skipped, `next_fire_at` is advanced by one interval, and an error is logged

### Requirement: _reconcile_registry re-seeds gateway schedule on restart

When `_reconcile_registry` restarts a stopped crew, it SHALL re-register all
tracked jobs from the transport registry into the gateway cron API, so the
gateway's schedule matches the transport's authoritative record.

#### Scenario: Gateway re-seeded after crew restart
- **WHEN** `_reconcile_registry` restarts a stopped crew
- **THEN** all jobs in that crew's transport registry `schedules` list are registered in the gateway cron API

### Requirement: schedule tool supports delay parameter

The `schedule` tool SHALL accept an optional `delay` integer parameter. When
provided, a one-shot cron job SHALL be created that fires once after the
specified number of seconds. The `dispatch` tool SHALL NOT accept a `delay`
parameter — `dispatch` is always immediate. `dispatch` SHALL always return a
`task_id`; `schedule` SHALL always return a `job_id`.

#### Scenario: One-shot delayed schedule
- **WHEN** `schedule(delay=300, message="run cleanup", agent="ghost", crew_id="my-crew")` is called
- **THEN** a one-shot cron job is created that fires in 300 seconds and returns `{"job_id": "<id>", "status": "scheduled", "delay": 300}`

#### Scenario: dispatch is always immediate
- **WHEN** `dispatch(task="run cleanup", crew_id="my-crew")` is called
- **THEN** the task is dispatched immediately and returns `{"task_id": "<id>", ...}` — no `delay` parameter exists on dispatch

### Requirement: Idempotent one-shot job deletion

Before deleting a fired one-shot job, the transport SHALL atomically set its registry entry to `enabled: false` and `next_fire_at: _NEVER_FIRE_AT` under `_registry_lock`, then issue the gateway DELETE. This safety gate applies regardless of dispatch outcome. Successful deletion MAY remove the entry; failure SHALL be logged at WARNING and the monitor SHALL never refire the job.

#### Scenario: One-shot job fires successfully, DELETE succeeds

- **WHEN** the schedule monitor fires a one-shot job and the task dispatch succeeds, and the subsequent gateway DELETE of the cron succeeds
- **THEN** the registry entry is marked disabled with `next_fire_at = _NEVER_FIRE_AT` before the DELETE is issued, and the job is not re-fired in any future cycle

#### Scenario: One-shot job fires, DELETE fails

- **WHEN** the schedule monitor fires a one-shot job and the gateway DELETE fails (network error, 404, or gateway timeout)
- **THEN** the registry entry has already been marked disabled with `next_fire_at = _NEVER_FIRE_AT`, the DELETE failure is logged at WARNING level, and the job is not re-fired in any subsequent schedule monitor cycle

#### Scenario: One-shot job replay in subsequent year is prevented

- **GIVEN** a one-shot job whose cron expression contains a wildcard year component (e.g. `30 14 12 9 *`)
- **WHEN** the schedule monitor fires it and the DELETE fails
- **THEN** the registry marks `enabled: false` and `next_fire_at = _NEVER_FIRE_AT` so the wildcard-year expression cannot cause a replay in the next calendar year

### Requirement: Schedule registry cleared on confirmed nuke
The transport schedule registry SHALL contain schedule entries only for crews that exist in the crew registry. When a crew is removed via `nuke(confirm=True)`, all entries in that crew's `schedules` list SHALL be removed from the transport registry as part of the same atomic registry write that removes the crew entry itself.

#### Scenario: Registry consistent after nuke
- **WHEN** `nuke(confirm=True)` is called for a crew and the nuke completes successfully
- **THEN** the transport registry contains no `schedules` entries for that crew, and the `_schedule_monitor` loop will not attempt to fire any jobs for the nuked crew in subsequent cycles

#### Scenario: Partial failure does not leave orphan schedule entries
- **WHEN** `nuke(confirm=True)` is called and one or more gateway `DELETE /api/crons/<job_id>` requests fail
- **THEN** the crew's schedule entries are still removed from the transport registry as part of the crew entry deletion — orphaned registry entries are not left behind due to individual gateway cancellation failures

### Requirement: Schedule tool supports per-job model override

`schedule` SHALL accept an optional `model` for cron, interval, and one-shot delay jobs. It SHALL retain and forward the pin on immediate, monitor-fired, and restart-reseeded runs. Validation and precedence SHALL match the `dispatch` model parameter.

#### Scenario: Schedule with a model override
- **WHEN** `schedule(interval=300, message="...", agent="ghost", crew_id="my-crew", model="claude-sonnet-5")` is called
- **THEN** the system forwards `model: "claude-sonnet-5"` in the `/api/crons` request body when creating the job

#### Scenario: Schedule with a model override on a one-shot delay job
- **WHEN** `schedule(delay=300, message="...", agent="ghost", crew_id="my-crew", model="claude-sonnet-5")` is called
- **THEN** the system forwards `model: "claude-sonnet-5"` in the one-shot job's `/api/crons` request body, the same as the `cron`/`interval` path

#### Scenario: Schedule without a model override
- **WHEN** `schedule` is called without a `model` parameter
- **THEN** the system omits `model` from the `/api/crons` request body, leaving persona/env-var model precedence unchanged

#### Scenario: Schedule model applies to immediate and transport-owned runs
- **WHEN** a scheduled job is created with `model="claude-sonnet-5"` and `fire_immediately` is true, or the job later fires through the transport schedule monitor or is re-registered after restart
- **THEN** each transport-issued request for that job includes `model: "claude-sonnet-5"`

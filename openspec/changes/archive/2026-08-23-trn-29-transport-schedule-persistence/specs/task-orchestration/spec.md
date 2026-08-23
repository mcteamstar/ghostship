## ADDED Requirements

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

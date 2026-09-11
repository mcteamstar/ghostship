# Task Orchestration Specification

## Purpose

Let an MCP client dispatch tasks to agent personas inside a crew, check on or collect their results, redirect or continue them, and schedule recurring tasks — the core interactive surface of the `ghostship` MCP server.

## Requirements

### Requirement: Task dispatch
The system SHALL dispatch a task to a named agent persona within a specified crew and return a task ID for later tracking. Every dispatched task SHALL be a dedicated (retained) run at the crew gateway, not a default shared run, so that a later forceful stop of that task cannot destroy session data shared with another task.

The system SHALL accept an optional `mode` parameter on `dispatch()` with one of three values:

- `"headless"` (default when the crew has no dashboard) — no `parent_session` is set on `/api/spawn`. Current behaviour, zero regression.
- `"anchored"` (default when the crew was launched with `dashboard=True`) — before dispatching, the system SHALL call `POST /api/chat/slots {"name": "<crew-id>"}` on the crew gateway to materialise the session in the Sessions list (409 if already exists is treated as success), then pass `parent_session="dashboard:<crew-id>"` on `/api/spawn`.
- `"free"` — before each task's dispatch, the system SHALL call `POST /api/chat/slots {"name": "<crew-id>-<8hex>"}` on the crew gateway to materialise a dedicated session slot, then pass `parent_session="dashboard:<crew-id>-<8hex>"` on `/api/spawn`. Each task gets its own visible session.

When `mode` is not explicitly provided, the system SHALL derive the default at dispatch time from the crew's current `dashboard_port` registry field: `"anchored"` if `dashboard_port` is set (dashboard is active), `"headless"` otherwise. This approach self-corrects automatically when the dashboard is enabled or disabled mid-flight — no stored default is needed.

The effective `mode` SHALL be echoed back in the `dispatch()` response.

#### Scenario: Dispatch to an existing crew
- **WHEN** `dispatch` is called with a `task`, an `agent` (defaulting to `ghost`), and a `crew_id` that exists
- **THEN** the system ensures the crew container is running, forwards the task to the crew's `/api/spawn` endpoint with a dedicated-run request, and returns a `task_id` with status `dispatched`, `created_at` as an ISO 8601 UTC timestamp, and `mode` echoing the effective mode

#### Scenario: Dispatch without crew_id when crews exist
- **WHEN** `dispatch` is called without `crew_id` and one or more crews are registered
- **THEN** the system returns an error listing the live crew IDs instead of guessing which crew to use

#### Scenario: Dispatch when no crews exist
- **WHEN** `dispatch` is called without `crew_id` and no crews are registered
- **THEN** the system returns an error instructing the caller to call `launch` first

#### Scenario: mode=anchored creates a session slot and attaches task to it
- **WHEN** `dispatch` is called with `mode="anchored"` (or defaulted to anchored via the crew's dashboard_port flag)
- **THEN** the system calls `POST /api/chat/slots {"name": "<crew-id>"}` on the crew gateway (treating 409 as success), then sends `/api/spawn` with `parent_session="dashboard:<crew-id>"`, and the response includes `"mode": "anchored"`

#### Scenario: mode=free creates a dedicated session slot per task
- **WHEN** `dispatch` is called with `mode="free"`
- **THEN** the system calls `POST /api/chat/slots {"name": "<crew-id>-<8hex>"}` on the crew gateway, then sends `/api/spawn` with `parent_session="dashboard:<crew-id>-<8hex>"` where `<8hex>` is the same transport-generated `uuid4().hex[:8]` suffix used for the slot, and the response includes `"mode": "free"` and `"parent_session"` echoing the slot name

#### Scenario: mode=headless sends no parent_session
- **WHEN** `dispatch` is called with `mode="headless"` (or the crew's default is headless)
- **THEN** the `/api/spawn` body does NOT include a `parent_session` field, and the response includes `"mode": "headless"`

#### Scenario: mode invalid value rejected
- **WHEN** `dispatch` is called with `mode` set to any value other than `"headless"`, `"anchored"`, or `"free"`
- **THEN** the system returns a validation error before dispatching any task

#### Scenario: Crew default inferred from active dashboard at dispatch time
- **WHEN** a crew has an active dashboard (`dashboard_url` is set in the registry) and `dispatch` is called with no explicit `mode`
- **THEN** the effective mode is `"anchored"` (derived from the live `dashboard_url` check, self-corrects when dashboard is toggled)

#### Scenario: Crew default is headless when dashboard is not active
- **WHEN** a crew has no active dashboard (`dashboard_url` is absent or null) and `dispatch` is called with no explicit `mode`
- **THEN** the effective mode is `"headless"` (derived from the live `dashboard_url` check)

### Requirement: Task status and collection
The system SHALL report a task's progress and result when polled, and SHALL list all tasks in a crew when no specific task is named. The system SHALL always include mail state in the pickup response without requiring any flag or option. The system SHALL support an optional `timeout_secs` parameter that, when greater than zero, polls until the task completes, the timeout elapses, or new Admiral mail arrives.

The system SHALL cap the internal poll window at `GA_PICKUP_MAX_POLL_SECS` (default 30s) regardless of the caller-supplied `timeout_secs` value. When the internal cap fires before the caller's `timeout_secs` has elapsed (i.e. the task is still running), the system SHALL return the current task state as a normal (non-error) JSON response with `"reason": "timeout"`. The MCP transport error path SHALL NOT be used for a clean timeout expiry.

The system SHALL read all crew mailboxes on every `pickup` call (all six persona mailboxes, `/var/mail/captain`, and `/var/mail/admiral`) and include subject lines and counts in the response. Only subject lines are returned — message bodies are not read. Reading mailboxes never modifies them.

What is reported back is tuned to how `pickup` was called:

- When `pickup` is called with a `task_id`: report the task's agent mailbox, captain, and admiral — subjects and counts for those three.
- When `pickup` is called without a `task_id` (crew-wide): report all persona mailboxes, captain, and admiral.

In both cases all 8 mailboxes are read; only the reported set differs.

#### Scenario: Poll a specific task
- **WHEN** `pickup` is called with a `task_id` and `crew_id`
- **THEN** the system returns the task's done state, turn count, last tool used, elapsed seconds, result, error, and outcome, plus the unread mail count for the agent that ran the task and the Admiral mail count, and `created_at`, `started_at`, `completed_at` ISO 8601 UTC timestamps (`null` when not yet reached)

#### Scenario: List all tasks in a crew
- **WHEN** `pickup` is called with a `crew_id` but no `task_id`
- **THEN** the system returns a dict containing the task list, a per-agent unread mail summary, and the Admiral mail count

#### Scenario: Poll a specific task reports agent, captain, and admiral subjects
- **WHEN** `pickup` is called with a `task_id` and `crew_id`
- **THEN** the response includes the existing fields plus `<agent>_mail: N`, `<agent>_subjects: [...]`, `captain_mail: N`, `captain_subjects: [...]`, `admiral_mail: N`, `admiral_subjects: [...]`

#### Scenario: List all tasks reports all persona, captain, and admiral subjects
- **WHEN** `pickup` is called with a `crew_id` but no `task_id`
- **THEN** the response includes `agent_subjects` with subject line summaries for all 8 mailboxes plus captain and admiral alongside the existing task list

#### Scenario: pickup with agent filter returns single-inbox subjects only
- **WHEN** `pickup` is called without a `task_id` and with `agent="ghost"`
- **THEN** the response includes only ghost's mailbox subjects and count — no task list, no other mailbox data

#### Scenario: pickup with agent filter for an empty mailbox
- **WHEN** `pickup` is called without a `task_id` and with `agent="reaper"` and reaper's mailbox is empty
- **THEN** the response includes `{"agent": "reaper", "subjects": [], "mail": 0}`

#### Scenario: pickup with invalid agent name returns an error
- **WHEN** `pickup` is called with `agent="admiral"` (not a persona mailbox)
- **THEN** the system returns an error indicating the agent name is not valid for this filter

#### Scenario: Poll a specific task with timeout
- **WHEN** `pickup` is called with a `task_id`, `crew_id`, and `timeout_secs` greater than zero, and the task completes before both `timeout_secs` and `GA_PICKUP_MAX_POLL_SECS` elapse
- **THEN** the system polls until the task is done, then returns the same shape as a zero-timeout pickup including mail state

#### Scenario: Timeout elapses before the task finishes
- **WHEN** `pickup` is called with a `task_id`, `crew_id`, and `timeout_secs` greater than zero, and the task is still not done when the poll window ends
- **THEN** the system returns the task's current (not-done) state as a **normal JSON response** (not a transport error) including mail state, with `"reason": "timeout"` in the response body

#### Scenario: Internal poll cap fires before caller timeout_secs
- **WHEN** `pickup` is called with `timeout_secs` greater than `GA_PICKUP_MAX_POLL_SECS` and the task does not complete within `GA_PICKUP_MAX_POLL_SECS`
- **THEN** the system returns the current task state as a normal JSON response with `"reason": "timeout"` — the caller MAY re-poll with another `pickup(timeout_secs=N)` call to continue waiting

#### Scenario: Early return on Admiral mail during polling
- **WHEN** `pickup` is called with `timeout_secs` greater than zero, and new Admiral mail arrives while polling
- **THEN** the system returns early with the current task state and `reason: "admiral_mail"` alongside the normal response fields

#### Scenario: Default timeout is zero (immediate return)
- **WHEN** `pickup` is called without specifying `timeout_secs`
- **THEN** the system checks once and returns immediately, defaulting `timeout_secs` to 0

### Requirement: Blocking wait on a single task
The system SHALL provide a `bridge` tool as a backward-compatible alias for `pickup(timeout_secs=...)`. `bridge` delegates entirely to `pickup` and preserves the same interface for existing callers. New callers SHOULD use `pickup(timeout_secs=...)` directly.

#### Scenario: Task finishes before the timeout
- **WHEN** `bridge` is called with a `task_id`, `crew_id`, and `timeout_secs`, and the task completes before `timeout_secs` elapses
- **THEN** the system returns the task's done state and mail counts as soon as `done` becomes `true`

#### Scenario: Timeout elapses before the task finishes
- **WHEN** `bridge` is called with a `task_id` and the task is still not done after `timeout_secs` has elapsed
- **THEN** the system returns the task's current (not-done) state without raising an error

#### Scenario: Crew is idle-stopped when bridge is called
- **WHEN** `bridge` is called against a crew that is currently idle-stopped
- **THEN** the system restarts the crew before beginning to poll, the same recovery `pickup` and `supply` already perform

#### Scenario: Waiting for any task in a crew to finish
- **WHEN** `bridge` is called with a `crew_id` but no `task_id`, and at least one task in that crew completes before `timeout_secs` elapses
- **THEN** the system returns that task's result as soon as any task's `done` becomes `true`

#### Scenario: Timeout elapses with no task done and no task_id given
- **WHEN** `bridge` is called with a `crew_id` but no `task_id`, and no task in that crew is done after `timeout_secs` has elapsed
- **THEN** the system returns the full crew task dict in the same shape `pickup` returns when called without a `task_id`

#### Scenario: Bridge does not accept multi-crew or multi-task requests
- **WHEN** `bridge` is called without a specific `crew_id`
- **THEN** the system returns a validation error

### Requirement: Steering running or completed tasks
The system SHALL redirect a still-running task in place, and SHALL resume a completed task's session with full prior context when steered again. Steering only takes effect at a turn boundary — it SHALL NOT interrupt a tool call already in flight inside the crew, unless the caller opts into a forceful stop. `steer`'s `task_id` SHALL be limited to tasks created via `dispatch` (`/api/spawn`) — a recurring job created via `schedule` has no such `task_id` and is not steerable through this tool.

#### Scenario: Steer a running task
- **WHEN** `steer` is called with a `task_id` whose task is not yet done and `force` is not set
- **THEN** the system sends the message to the task's `/steer` endpoint and returns action `steered`

#### Scenario: Continue a completed task
- **WHEN** `steer` is called with a `task_id` whose task is already done
- **THEN** the system calls the task's `/continue` endpoint with the new message, resuming the same session with its prior context intact, and returns action `redeployed` — regardless of whether `force` was set, since there is nothing running left to stop

#### Scenario: Steering a task stuck in a blocking tool call
- **WHEN** `steer` is called for a task that is currently inside a long-running or unbounded blocking tool call (e.g. an infinite shell polling loop) and `force` is not set
- **THEN** the steer call itself succeeds (the message is accepted by the endpoint), but the message does not reach the agent until that tool call returns — which, for a genuinely unbounded loop, may never happen without `force` or external intervention (e.g. `nuke` and redispatch)

#### Scenario: Forcefully stopping a stuck task
- **WHEN** `steer` is called with `force` set to true for a `task_id` whose task is not yet done
- **THEN** the system stops the task's underlying process (rather than waiting for a turn boundary), then resumes the same session with the new message via the task's `/continue` endpoint, and returns action `force_redeployed`

#### Scenario: A recurring job has no task_id to steer
- **WHEN** an Admiral wants to change what a `schedule`-created recurring job does
- **THEN** `steer` cannot be used, since the job has a `job_id`, not a `task_id` — a new `schedule` call, or for a standing-orders Captain check-in a `captain(action="order", ...)` call, is the only path

### Requirement: Recurring task scheduling
The system SHALL schedule a recurring task on a crew using either a cron expression or a fixed interval in seconds (parameter named `interval`), and SHALL reject a request that supplies both or neither. The system SHALL default `agent` to `ghost` when not specified, matching `dispatch`'s default; a Captain check-in that should run as Raven SHALL set `agent` explicitly. The system SHALL accept a `fire_immediately` boolean parameter that controls whether the job's task is dispatched once immediately upon creation, before the first scheduled interval or cron tick fires.

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

### Requirement: Captain standing-orders check-in
The `captain(action="order")` call SHALL accept `interval` (in seconds, replacing `every_secs`) and `fire_immediately` with the same defaulting logic as `schedule()`. When `fire_immediately` is true and the Captain check-in is newly created (not resumed from a previously paused state), the system SHALL dispatch Raven immediately after registering the job.

#### Scenario: Captain order with interval and default fire_immediately
- **WHEN** `captain(action="order")` is called with `interval` set and `fire_immediately` not specified
- **THEN** the system defaults `fire_immediately` to `true`, registers the recurring Captain check-in, and dispatches Raven immediately

#### Scenario: Captain order resumed does not fire immediately
- **WHEN** `captain(action="order")` is called to resume a previously paused Captain check-in
- **THEN** the system does not dispatch immediately regardless of `fire_immediately`, since this is a resume not a new creation

#### Scenario: Captain order with every_secs is rejected
- **WHEN** `captain(action="order")` is called with `every_secs` as the parameter name
- **THEN** the system returns a validation error indicating the parameter has been renamed to `interval`

### Requirement: Crew listing
The system SHALL list every registered crew with its status, creation time, and active agent tasks.

#### Scenario: List crews with a mix of states
- **WHEN** `crews` is called while some crews are running and others are stopped or idle
- **THEN** the system returns an entry per crew with its known metadata, and an empty `agents` list for any crew whose gateway cannot currently be reached

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

### Requirement: Dispatch tool supports delay parameter

The `dispatch` tool SHALL accept an optional `delay` integer parameter. When provided, the task SHALL NOT be dispatched immediately but SHALL be scheduled as a one-shot job that fires once after the specified number of seconds. The minimum value SHALL be 1. The implementation SHALL use a cron expression computed from `now + delay` seconds so the job fires at a specific UTC time. The tool SHALL return the scheduled `job_id` along with `status: "delayed"` and the `delay` value.

#### Scenario: Dispatch with delay

- **WHEN** the Admiral calls `dispatch(task="run cleanup", agent="ghost", crew_id="my-crew", delay=300)`
- **THEN** the task is not dispatched immediately, a one-shot cron job is created to fire in 300 seconds, and the tool returns `{"task_id": null, "job_id": "<id>", "crew_id": "my-crew", "status": "delayed", "delay": 300, "agent": "ghost"}`

#### Scenario: Dispatch with invalid delay

- **WHEN** the Admiral calls `dispatch(task="run cleanup", crew_id="my-crew", delay=0)`
- **THEN** the tool returns `{"error": "delay must be >= 1"}`

### Requirement: transport://jobs resource exposes scheduled jobs

The transport server SHALL expose a `transport://jobs` MCP resource that returns the list of all scheduled jobs across all running crews. Each job entry SHALL include `job_id`, `crew_id`, `name`, `schedule`, `agent`, `enabled`, `last_run`, and `last_status` fields. The resource SHALL be readable by any MCP client connected to the transport.

#### Scenario: Read jobs resource with active crews

- **WHEN** an MCP client reads `transport://jobs` and there are two crews with a total of three scheduled jobs
- **THEN** the resource returns a plain-text formatted listing of all three jobs grouped by crew, including each job's id, name, schedule expression, agent, enabled state, and last run timestamp

#### Scenario: Read jobs resource with no running crews

- **WHEN** an MCP client reads `transport://jobs` and no crews are running
- **THEN** the resource returns `"No running crews found."` or an empty listing

### Requirement: Persona allowlist for task submission
The system SHALL accept `agent` values only from the six Ghost Academy personas `ghost`, `spectre`, `banshee`, `wraith`, `reaper`, and `raven` in both `dispatch` and `schedule`. It SHALL reject every other value before contacting a crew API, including known built-in or custom KiroCrew agent names.

#### Scenario: Dispatch to a standard persona
- **WHEN** `dispatch` is called with `agent` equal to one of the six standard persona names
- **THEN** the transport forwards the task to the crew API and returns the normal dispatched response

#### Scenario: Schedule a standard persona
- **WHEN** `schedule` is called with `agent` equal to one of the six standard persona names
- **THEN** the transport forwards the recurring job to the crew API and returns the normal scheduled response

#### Scenario: Reject a non-roster agent on dispatch
- **WHEN** `dispatch` is called with an agent name outside the six-persona roster, including a known `kirocrew*` agent
- **THEN** the transport returns a clear validation error and does not call the crew API

#### Scenario: Reject a non-roster agent on schedule
- **WHEN** `schedule` is called with an agent name outside the six-persona roster
- **THEN** the transport returns a clear validation error and does not create a recurring job

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

### Requirement: Schedule registry cleared on confirmed nuke
The transport schedule registry SHALL contain schedule entries only for crews that exist in the crew registry. When a crew is removed via `nuke(confirm=True)`, all entries in that crew's `schedules` list SHALL be removed from the transport registry as part of the same atomic registry write that removes the crew entry itself.

#### Scenario: Registry consistent after nuke
- **WHEN** `nuke(confirm=True)` is called for a crew and the nuke completes successfully
- **THEN** the transport registry contains no `schedules` entries for that crew, and the `_schedule_monitor` loop will not attempt to fire any jobs for the nuked crew in subsequent cycles

#### Scenario: Partial failure does not leave orphan schedule entries
- **WHEN** `nuke(confirm=True)` is called and one or more gateway `DELETE /api/crons/<job_id>` requests fail
- **THEN** the crew's schedule entries are still removed from the transport registry as part of the crew entry deletion — orphaned registry entries are not left behind due to individual gateway cancellation failures

### Requirement: Dispatch tool supports per-task model override

The `dispatch` tool SHALL accept an optional `model` string parameter. When provided, it SHALL be forwarded as `model` in the `/api/spawn` request body, pinning that one task's model regardless of the dispatched persona's configured `model` in its agent JSON. When omitted, the request body SHALL NOT include a `model` field and existing precedence (`KC_MODEL_OVERRIDE` > per-agent `model` > `KC_MODEL_DEFAULT` > KiroCrew built-in) is unaffected. The system SHALL validate `model` before forwarding it: reject a non-string value, and reject a value exceeding the crew gateway's own model-name length/format bounds, returning a clear transport-level error without contacting the crew API.

#### Scenario: Dispatch with a model override
- **WHEN** `dispatch(task="...", agent="ghost", crew_id="my-crew", model="claude-opus-5")` is called
- **THEN** the system forwards `model: "claude-opus-5"` in the `/api/spawn` request body, and the response includes the normal dispatched fields

#### Scenario: Dispatch without a model override
- **WHEN** `dispatch` is called without a `model` parameter
- **THEN** the system omits `model` from the `/api/spawn` request body, leaving persona/env-var model precedence unchanged

#### Scenario: Dispatch with a malformed model value
- **WHEN** `dispatch` is called with a `model` value that is not a string, or exceeds the crew gateway's model-name length/format bounds
- **THEN** the system returns a validation error and does not contact the crew API

#### Scenario: A per-dispatch model outranks KC_MODEL_OVERRIDE
- **WHEN** `dispatch` is called with a `model` parameter AND the crew's `KC_MODEL_OVERRIDE` env var is set to a different value
- **THEN** the per-call `model` value is what gets forwarded to `/api/spawn` and served for that task — `KC_MODEL_OVERRIDE` is not an absolute ceiling once a caller supplies an explicit per-dispatch `model` (an accepted trade-off, not a defect; see design.md)

### Requirement: Schedule tool supports per-job model override

The `schedule` tool SHALL accept an optional `model` string parameter, for `cron`, `interval`, and `delay` (one-shot) job creation alike. When provided, it SHALL be forwarded as `model` in the `/api/crons` request body, pinning that one recurring or one-shot job's model. The transport SHALL retain the pin with the scheduled job and SHALL include it when re-registering a missing job after a crew or transport restart and when firing a due job through the transport-owned schedule monitor. If `fire_immediately` causes an immediate `/api/spawn`, that first run SHALL receive the same `model` when one was provided. The same validation and precedence rules as the `dispatch` tool's `model` parameter apply.

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

### Requirement: Captain standing-orders check-in supports model override

The `captain(action="order")` call SHALL accept an optional `model` string parameter, forwarded as `model` in the `/api/crons` request body when a new standing-orders check-in job is created. When a new job is configured to `fire_immediately`, the immediate Raven `/api/spawn` SHALL receive the same model. The transport SHALL retain the pin for restart re-seeding and transport-owned schedule-monitor ticks. The parameter's format SHALL be validated on every call regardless of action, and an invalid value SHALL return an error even when resuming. A syntactically valid value SHALL have no effect when resuming a previously paused check-in, since no new job is created in that path; an existing pin SHALL remain unchanged.

#### Scenario: Captain order with a model override on a new check-in
- **WHEN** `captain(crew_id="my-crew", action="order", template="sdd", change_name="...", interval=300, model="claude-opus-5")` creates a new check-in job
- **THEN** the system forwards `model: "claude-opus-5"` in the `/api/crons` request body for that job

#### Scenario: Captain order with a valid model override on a resumed check-in
- **WHEN** `captain(action="order", model="claude-opus-5")` is called to resume a previously paused check-in
- **THEN** the system resumes the existing job unchanged and does not apply the `model` parameter, since no new job is created

#### Scenario: Captain order with an invalid model override on a resumed check-in
- **WHEN** `captain(action="order", model="bad model!")` is called to resume a previously paused check-in
- **THEN** the system returns an error and does not resume the job, since the parameter's format is still validated regardless of action

#### Scenario: Captain order model applies to the immediate Raven run
- **WHEN** a new Captain check-in is created with `interval=300`, `fire_immediately=true`, and `model="claude-opus-5"`
- **THEN** the cron creation request and the immediate Raven `/api/spawn` request both carry `model: "claude-opus-5"`

### Requirement: dispatch accepts tasks list as an alternative overload

The `dispatch` tool SHALL accept `tasks: list[str]` as an alternative to `task: str`. The two parameters SHALL be mutually exclusive. When `tasks` is provided, all dispatch semantics (agent validation, model validation, crew lookup, `_ensure_crew_running`) apply identically to each task in the list before any `/api/spawn` call is made. All tasks in one batch share the same `agent`, `model`, `crew_id`, and `mode`.

The `mode` parameter SHALL apply uniformly across all tasks in a batch. For `"free"` mode, each task in the batch receives its own `parent_session` keyed to a transport-generated `uuid4().hex[:8]` suffix (not the gateway-assigned task ID, which is unavailable before the `/api/spawn` call).

See `specs/batch-dispatch/spec.md` for the full batch dispatch contract, registry record, and error scenarios.

#### Scenario: Batch dispatch uses same validation as single dispatch

- **WHEN** `dispatch` is called with `tasks=[...]` and an agent not on the six-persona roster
- **THEN** the system returns a validation error without dispatching any task — identical behaviour to `dispatch(task=..., agent="invalid")`

#### Scenario: Batch dispatch records last_task_at per task

- **WHEN** `dispatch` is called with `tasks=[...]` and all `/api/spawn` calls succeed
- **THEN** the transport updates `last_task_at` in the crew registry for each successfully dispatched task, using the timestamp of that task's `/api/spawn` response

#### Scenario: Batch dispatch with anchored mode uses one parent_session for all tasks

- **WHEN** `dispatch` is called with `tasks=[...]` and `mode="anchored"`
- **THEN** every task in the batch is sent to `/api/spawn` with the same `parent_session="dashboard:<crew-id>"`

#### Scenario: Batch dispatch with free mode gives each task its own parent_session

- **WHEN** `dispatch` is called with `tasks=[...]` and `mode="free"`
- **THEN** each task is sent with `parent_session="dashboard:<crew-id>-<8hex>"` where `<8hex>` is a distinct transport-generated `uuid4().hex[:8]` suffix per task, and `task_parent_sessions` in the response maps each `task_id` to its slot name

### Requirement: pickup accepts task_ids list for batch collection

The `pickup` tool SHALL accept `task_ids: list[str]` as an alternative to `task_id: str`. The two parameters SHALL be mutually exclusive. When `task_ids` is provided, the tool routes to `_pickup_batch` in `lifecycle.py`, which polls each task ID sequentially per round and aggregates results. The existing `GA_PICKUP_MAX_POLL_SECS` cap applies per round across all members.

See `specs/batch-dispatch/spec.md` for the full blocking batch pickup contract and lost-member semantics.

#### Scenario: pickup(task_ids=...) inherits the existing timeout cap

- **WHEN** `pickup` is called with `task_ids=[...]` and `timeout_secs` greater than `GA_PICKUP_MAX_POLL_SECS`
- **THEN** each polling round completes within `GA_PICKUP_MAX_POLL_SECS`, the system returns with `"reason": "timeout"`, and the caller may re-poll to continue waiting — identical to the single-task `pickup` internal-cap behaviour

#### Scenario: pickup(task_ids=...) without crew_id returns an error

- **WHEN** `pickup` is called with `task_ids=[...]` and no `crew_id`
- **THEN** the system returns `{"error": "crew_id is required"}` — same behaviour as single-task pickup without crew_id

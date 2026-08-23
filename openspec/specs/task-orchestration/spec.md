# Task Orchestration Specification

## Purpose

Let an MCP client dispatch tasks to agent personas inside a crew, check on or collect their results, redirect or continue them, and schedule recurring tasks — the core interactive surface of the `ghostship` MCP server.

## Requirements

### Requirement: Task dispatch
The system SHALL dispatch a task to a named agent persona within a specified crew and return a task ID for later tracking. Every dispatched task SHALL be a dedicated (retained) run at the crew gateway, not a default shared run, so that a later forceful stop of that task cannot destroy session data shared with another task.

#### Scenario: Dispatch to an existing crew
- **WHEN** `dispatch` is called with a `task`, an `agent` (defaulting to `ghost`), and a `crew_id` that exists
- **THEN** the system ensures the crew container is running, forwards the task to the crew's `/api/spawn` endpoint with a dedicated-run request, and returns a `task_id` with status `dispatched`

#### Scenario: Dispatch without crew_id when crews exist
- **WHEN** `dispatch` is called without `crew_id` and one or more crews are registered
- **THEN** the system returns an error listing the live crew IDs instead of guessing which crew to use

#### Scenario: Dispatch when no crews exist
- **WHEN** `dispatch` is called without `crew_id` and no crews are registered
- **THEN** the system returns an error instructing the caller to call `launch` first

### Requirement: Task status and collection
The system SHALL report a task's progress and result when polled, and SHALL list all tasks in a crew when no specific task is named. The system SHALL always include mail state in the pickup response without requiring any flag or option. The system SHALL support an optional `timeout_secs` parameter that, when greater than zero, polls until the task completes, the timeout elapses, or new Admiral mail arrives.

The system SHALL read all crew mailboxes on every `pickup` call (all six persona mailboxes, `/var/mail/captain`, and `/var/mail/admiral`) and include subject lines and counts in the response. Only subject lines are returned — message bodies are not read. Reading mailboxes never modifies them.

What is reported back is tuned to how `pickup` was called:

- When `pickup` is called with a `task_id`: report the task's agent mailbox, captain, and admiral — subjects and counts for those three.
- When `pickup` is called without a `task_id` (crew-wide): report all persona mailboxes, captain, and admiral.

In both cases all 8 mailboxes are read; only the reported set differs.

#### Scenario: Poll a specific task
- **WHEN** `pickup` is called with a `task_id` and `crew_id`
- **THEN** the system returns the task's done state, turn count, last tool used, elapsed seconds, result, error, and outcome, plus the unread mail count for the agent that ran the task and the Admiral mail count

#### Scenario: List all tasks in a crew
- **WHEN** `pickup` is called with a `crew_id` but no `task_id`
- **THEN** the system returns a dict containing the task list, a per-agent unread mail summary, and the Admiral mail count

#### Scenario: Poll a specific task reports agent, captain, and admiral subjects
- **WHEN** `pickup` is called with a `task_id` and `crew_id`
- **THEN** the response includes the existing fields plus `<agent>_mail: N`, `<agent>_subjects: [...]`, `captain_mail: N`, `captain_subjects: [...]`, `admiral_mail: N`, `admiral_subjects: [...]`

#### Scenario: List all tasks reports all persona, captain, and admiral subjects
- **WHEN** `pickup` is called with a `crew_id` but no `task_id`
- **THEN** the response includes subject line summaries for all persona mailboxes plus captain and admiral alongside the existing task list

#### Scenario: Poll a specific task with timeout
- **WHEN** `pickup` is called with a `task_id`, `crew_id`, and `timeout_secs` greater than zero, and the task completes before the timeout elapses
- **THEN** the system polls until the task is done, then returns the same shape as a zero-timeout pickup including mail state

#### Scenario: Timeout elapses before the task finishes
- **WHEN** `pickup` is called with a `task_id`, `crew_id`, and `timeout_secs` greater than zero, and the task is still not done after `timeout_secs` elapses
- **THEN** the system returns the task's current (not-done) state including mail state, without raising an error

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

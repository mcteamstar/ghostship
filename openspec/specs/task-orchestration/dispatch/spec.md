# task-orchestration/dispatch Specification

## Purpose

Defines task admission, dispatch and member-slot routing.

## Requirements

### Requirement: Batch dispatch returns per-task results

The system SHALL dispatch each task sequentially to the named crew with the same agent, model, and slot options, record the batch, and return its `batch_id` and `task_ids`. Partial success SHALL be reported with the assigned task IDs; the response SHALL omit `task_slots`.

#### Scenario: Batch dispatch — all tasks start

- **WHEN** `dispatch` is called with `tasks=["task A", "task B", "task C"]`, a valid `crew_id`, and valid `agent`
- **THEN** the system dispatches each task to `/api/spawn`, records a batch entry with `batch_id`, `task_ids`, `status: "pending"`, and `created_at`, and returns `{"batch_id": "<id>", "task_ids": ["<id1>", "<id2>", "<id3>"], "crew_id": "<crew_id>", "status": "dispatched", "agent": "<agent>", "created_at": "<ts>"}`

#### Scenario: Batch dispatch — crew dies mid-batch

- **WHEN** `dispatch` is called with `tasks=[...]` and the crew container becomes unreachable after some but not all `/api/spawn` calls have returned
- **THEN** the system records a `partial` batch entry for the tasks that succeeded and returns a partial result with `status: "partial"`, the `task_ids` that were assigned, and an `error` field naming the failure point — the tasks that never received a `task_id` are the lost members

#### Scenario: Batch dispatch reuses single-task options
- **WHEN** `dispatch` is called with a valid batch, an optional model override, and `slot` set to `None` or `False`
- **THEN** every task uses the same agent, model, and slot option, and the response contains no `task_slots` field

### Requirement: Batch registry record tracks member status

The transport registry SHALL maintain a `batches` list per crew entry in `crews.json`. Each batch entry SHALL include `batch_id` (UUID), `task_ids` (list of string), `created_at` (ISO 8601 UTC), and `status` (`pending` | `partial` | `complete`). When all batch tasks complete, the batch status SHALL be updated to `complete`. Batch records SHALL be removed atomically when the associated crew is nuked.

#### Scenario: Batch record written at dispatch time

- **WHEN** a batch dispatch completes (all or partial)
- **THEN** a batch entry is written to `crews.json` under `crews[crew_id]["batches"]` with the fields listed above

#### Scenario: Batch record removed on nuke

- **WHEN** `nuke(confirm=True)` is called for a crew
- **THEN** the crew's `batches` list is removed as part of the same atomic registry write that removes the crew entry

### Requirement: Gateway refusal preserves accepted batch members

Batch dispatch SHALL retain and persist prior accepted task IDs when a later spawn is refused by the gateway.

#### Scenario: Gateway refuses a later spawn

- **WHEN** one or more spawns succeed before a later gateway refusal
- **THEN** dispatch returns a partial result with those task IDs and the sanitized failure
- **AND** the registry retains those IDs for pickup without repeating the accepted spawns

#### Scenario: Gateway refuses the first spawn

- **WHEN** the gateway refuses the first spawn
- **THEN** dispatch returns the existing failure response without claiming any accepted members

### Requirement: ghostship-spawn covers the gateway operations the kirocrew CLI does not
Crews selecting `ghostship-spawn` SHALL provide commands to dispatch retained tasks from stdin, show task status, steer running tasks from stdin, and continue finished tasks from stdin. Each SHALL print gateway JSON and use only fixed `/api/spawn` paths on its own loopback gateway; destination URL, host, port, or path SHALL NOT be configurable through arguments, stdin, or environment.

#### Scenario: Dispatch a named persona
- **WHEN** an agent runs `ghostship-spawn ghost` with the task text on standard input
- **THEN** a retained ghost task is created on the crew's gateway with exactly that task text, and standard output carries the gateway's JSON response, including the new task's `id` field

#### Scenario: Steer and continue use the same command
- **WHEN** an agent runs `ghostship-spawn --steer <task_id>` or `ghostship-spawn --continue <task_id>` with text on standard input
- **THEN** the running task is redirected, or the finished task is resumed, with that text, and the gateway's JSON response is written to standard output

#### Scenario: Destination cannot be redirected
- **WHEN** `ghostship-spawn` is run with any arguments, input or environment
- **THEN** every request it makes goes to the crew's own loopback gateway at an `/api/spawn` path, and to nowhere else

#### Scenario: Status lookup
- **WHEN** an agent runs `ghostship-spawn --status <task_id>`
- **THEN** standard output carries that task's detail as returned by the gateway

### Requirement: ghostship-spawn handles gateway authentication itself
`ghostship-spawn` SHALL authenticate with the crew's dashboard session cookie and the gateway's allowed origin, read inside the helper. It SHALL NOT send `X-Internal-Secret` or `X-Session-Key`, SHALL NOT read `.local_secret`, and SHALL NOT write the cookie value to standard output, standard error or any file.

#### Scenario: No credential in the agent's command
- **WHEN** an agent dispatches a persona with `ghostship-spawn`
- **THEN** the command the agent runs contains no cookie value, secret file path, `curl` invocation or `@file` data argument

#### Scenario: Cookie never echoed
- **WHEN** `ghostship-spawn` succeeds or fails for any reason
- **THEN** neither its output nor its error output contains the cookie value

### Requirement: ghostship-spawn reports failures plainly
`ghostship-spawn` SHALL exit non-zero, with a one-line error on standard error, when its arguments are invalid, the task text is empty, the cookie cannot be read, or the gateway returns a non-2xx response. For a gateway error it SHALL include the HTTP status and the response body.

#### Scenario: Gateway refuses the request
- **WHEN** the gateway returns a non-2xx status to a `ghostship-spawn` call
- **THEN** the command exits non-zero and its error output names the HTTP status and includes the response body, without the cookie

#### Scenario: Empty task text
- **WHEN** `ghostship-spawn <persona>` is run with empty standard input
- **THEN** it exits non-zero without calling the gateway

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

### Requirement: Dispatch tool supports per-task model override

`dispatch` SHALL accept an optional `model` string and forward it for that task. Before contacting the crew API, it SHALL reject non-strings and values outside gateway model-name bounds. When omitted, it SHALL omit `model` and preserve precedence: `KC_MODEL_OVERRIDE`, agent model, `KC_MODEL_DEFAULT`, then gateway default.

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

### Requirement: Dispatch accepts one task or a bounded batch

The `dispatch` tool SHALL accept either `task` for one task or a mutually exclusive `tasks` list within the configured batch limits. The batch shares the crew, agent, model and resolved slot. Partial acceptance and the batch response and registry contract apply to all batch submissions.

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

#### Scenario: Batch dispatch uses same validation as single dispatch

- **WHEN** `dispatch` is called with `tasks=[...]` and an agent not on the six-persona roster
- **THEN** the system returns a validation error without dispatching any task

#### Scenario: Batch dispatch records last_task_at per task

- **WHEN** `dispatch` is called with `tasks=[...]` and all `/api/spawn` calls succeed
- **THEN** the transport updates `last_task_at` in the crew registry for each successfully dispatched task

#### Scenario: Enrolled batch uses one member slot by default
- **WHEN** `dispatch` is called with `tasks=[...]` and no `slot` for an enrolled persona
- **THEN** every `/api/spawn` request uses the same `parent_session="dashboard:member-<slug>"` and the response identifies that member slot

#### Scenario: Unenrolled batch is headless by default
- **WHEN** `dispatch` is called with `tasks=[...]` and no `slot` for an unenrolled persona
- **THEN** no `/api/spawn` request has a `parent_session` and the response has `slot: null`

#### Scenario: False forces every batch task headless
- **WHEN** `dispatch` is called with `tasks=[...]` and `slot=False` for an enrolled persona
- **THEN** no `/api/spawn` request has a `parent_session` and the response has `slot: null`

#### Scenario: Legacy True shares the default member slot
- **WHEN** `dispatch` is called with `tasks=[...]` and `slot=True` for an enrolled persona
- **THEN** the resolver logs a warning, every task uses the same member slot as `slot=None`, and no per-task slots are created

#### Scenario: Named batch slots are rejected
- **WHEN** `dispatch` is called with `tasks=[...]` and `slot="my-batch"`
- **THEN** the boolean-or-null tool input contract rejects the request and no named session is created

### Requirement: Dispatch routes member slots by enrollment

The system SHALL dispatch a task to a named persona in a specified crew as a dedicated retained run and return a task ID. `slot=None` routes enrolled personas to their pre-created member DM slot and leaves unenrolled personas headless. `slot=False` forces headless dispatch.

Legacy `True` SHALL emit a warning and use the default enrollment-based resolution. It SHALL never create a legacy session.

#### Scenario: Dispatch to an existing crew
- **WHEN** dispatch is called with a task, an agent, and an existing `crew_id`
- **THEN** the system ensures the crew is running, sends a dedicated-run request to `/api/spawn`, and returns a task ID, dispatched status, creation timestamp, and resolved slot

#### Scenario: Dispatch without crew_id when crews exist
- **WHEN** dispatch is called without `crew_id` and one or more crews are registered
- **THEN** the system returns an error listing live crew IDs instead of guessing

#### Scenario: Dispatch when no crews exist
- **WHEN** dispatch is called without `crew_id` and no crews are registered
- **THEN** the system returns an error instructing the caller to launch a crew first

#### Scenario: Enrolled persona uses its member slot by default
- **WHEN** dispatch is called without `slot` for an enrolled persona
- **THEN** `/api/spawn` uses `parent_session="dashboard:member-<slug>"` and the response identifies that member slot

#### Scenario: Unenrolled persona is headless by default
- **WHEN** dispatch is called without `slot` for an unenrolled persona
- **THEN** `/api/spawn` has no `parent_session` and the response has `slot: null`

#### Scenario: Explicit false forces headless dispatch
- **WHEN** dispatch is called with `slot=False` for an enrolled persona
- **THEN** `/api/spawn` has no `parent_session` and the response has `slot: null`

#### Scenario: Dashboard allocation does not choose a bridge slot
- **WHEN** a crew has a dashboard port and an enrolled persona is dispatched without a `slot` argument
- **THEN** the task uses the persona's member DM slot, not a shared bridge slot

#### Scenario: No dashboard port does not change enrollment-based routing
- **WHEN** a crew has no dashboard port and an enrolled persona is dispatched without a `slot` argument
- **THEN** the task uses its pre-created member DM slot

#### Scenario: True does not create a per-task slot
- **WHEN** dispatch is called with `slot=True`
- **THEN** the resolver logs a warning, applies the `slot=None` enrollment-based routing, and creates no per-task slot

#### Scenario: String-valued slots are invalid tool inputs
- **WHEN** an MCP dispatch request supplies a string value for `slot`
- **THEN** the boolean-or-null tool input contract rejects the request and no named session is created

#### Scenario: slot=True logs a warning and resolves as None
- **WHEN** `dispatch()` is called with `slot=True`
- **THEN** the transport logs a WARNING indicating `slot=True` is not a valid value
- **THEN** the dispatch proceeds as if `slot=None` was passed

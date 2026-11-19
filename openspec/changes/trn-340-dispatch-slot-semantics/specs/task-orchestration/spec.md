# Spec Delta

## ADDED Requirements

### Requirement: Task dispatch and member-slot routing

The system SHALL dispatch a task to a named persona in a specified crew as a dedicated retained run and return a task ID. `slot=None` routes enrolled personas to their pre-created member DM slot and leaves unenrolled personas headless. `slot=False` forces headless dispatch.

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

### Requirement: Legacy slot values do not create legacy sessions

`slot=True` SHALL NOT create a per-task slot; the current resolver warns and applies the `slot=None` routing. String-valued `slot` inputs are invalid under the MCP tool's boolean-or-null input schema and SHALL NOT create named sessions.

#### Scenario: True does not create a per-task slot
- **WHEN** dispatch is called with `slot=True`
- **THEN** the resolver logs a warning, applies the `slot=None` enrollment-based routing, and creates no per-task slot

#### Scenario: String-valued slots are invalid tool inputs
- **WHEN** an MCP dispatch request supplies a string value for `slot`
- **THEN** the boolean-or-null tool input contract rejects the request and no named session is created

## MODIFIED Requirements

### Requirement: dispatch accepts tasks list as an alternative overload

The `dispatch` tool SHALL accept `tasks: list[str]` as an alternative to `task: str`. The two parameters SHALL be mutually exclusive. When `tasks` is provided, all dispatch semantics apply identically to each task in the list. All tasks in one batch share the same `agent`, `model`, `slot`, and `crew_id`.

The `slot` parameter SHALL apply uniformly across all tasks in a batch. The transport SHALL resolve the slot once: `slot=None` routes all tasks for an enrolled persona to the same pre-created member DM slot and leaves all tasks for an unenrolled persona headless; `slot=False` forces every task headless. Legacy `slot=True` SHALL NOT create per-task slots; the resolver warns and treats it as `slot=None`, sharing that resolved behavior across the batch. String-valued slots are invalid under the MCP tool's boolean-or-null input schema and SHALL be rejected.

See `specs/batch-dispatch/spec.md` for the full batch dispatch contract.

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

#### Scenario: Batch dispatch with slot=True gives each task its own slot
- **WHEN** `dispatch` is called with `tasks=[...]` and `slot=True` for an enrolled persona
- **THEN** the resolver logs a warning, every task uses the same member slot as `slot=None`, and no per-task slots are created

#### Scenario: Batch dispatch with named slot shares one session for all tasks
- **WHEN** `dispatch` is called with `tasks=[...]` and `slot="my-batch"`
- **THEN** the boolean-or-null tool input contract rejects the request and no named session is created

## REMOVED Requirements

### Requirement: Task dispatch

**Reason**: Its bridge, arbitrary slot, and dashboard-port-derived defaults no longer match the dispatch tool contract.

**Migration**: Omit `slot` to use enrollment-based member-slot or headless resolution; pass `slot=False` to force headless dispatch. Do not use `slot=True` as a per-task slot mode or pass string-valued slots.

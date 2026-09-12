# Task Orchestration — Delta Spec (trn-147-dispatch-slot)

Updates to the `task-orchestration` capability.

## MODIFIED Requirements

### Requirement: Task dispatch

The system SHALL dispatch a task to a named agent persona within a specified crew and return a task ID for later tracking. Every dispatched task SHALL be a dedicated (retained) run at the crew gateway, not a default shared run, so that a later forceful stop of that task cannot destroy session data shared with another task.

The system SHALL accept an optional `slot` parameter on `dispatch()`:

- `slot=None` (default, no dashboard active) — no `parent_session` is set on `/api/spawn`. Task is invisible in the dashboard. Zero regression.
- `slot="bridge"` (default, dashboard active) — before dispatching, the system SHALL call `POST /api/chat/slots {"name": "bridge"}` on the crew gateway (treating 409 as success), then pass `parent_session="dashboard:bridge"` on `/api/spawn`. All tasks using this default share the crew's `"bridge"` session.
- `slot=True` — before dispatching, the system SHALL generate a unique slot name (`uuid4().hex[:8]` suffix), call `POST /api/chat/slots {"name": "<suffix>"}`, then pass `parent_session="dashboard:<suffix>"` on `/api/spawn`. Each task gets its own dedicated visible session.
- `slot="<name>"` — before dispatching, the system SHALL call `POST /api/chat/slots {"name": "<name>"}` (treating 409 as success), then pass `parent_session="dashboard:<name>"`. Multiple dispatches with the same slot name share one session.

When `slot` is not explicitly provided, the system SHALL derive the default at dispatch time from the crew's current `dashboard_port` registry field: `"bridge"` if `dashboard_port` is set, `None` otherwise.

The resolved slot name (or null when headless) SHALL be echoed back in the `dispatch()` response as `"slot"`.

The `mode` parameter is removed. Callers previously passing `mode="headless"` should pass `slot=None`; `mode="anchored"` → `slot="bridge"`; `mode="free"` → `slot=True`.

#### Scenario: Dispatch to an existing crew

- **WHEN** `dispatch` is called with a `task`, an `agent` (defaulting to `ghost`), and a `crew_id` that exists
- **THEN** the system ensures the crew container is running, forwards the task to the crew's `/api/spawn` endpoint with a dedicated-run request, and returns a `task_id` with status `dispatched`, `created_at` as an ISO 8601 UTC timestamp, and `slot` echoing the resolved slot name (or null)

#### Scenario: Dispatch without crew_id when crews exist

- **WHEN** `dispatch` is called without `crew_id` and one or more crews are registered
- **THEN** the system returns an error listing the live crew IDs instead of guessing which crew to use

#### Scenario: Dispatch when no crews exist

- **WHEN** `dispatch` is called without `crew_id` and no crews are registered
- **THEN** the system returns an error instructing the caller to call `launch` first

#### Scenario: slot=None sends no parent_session

- **WHEN** `dispatch` is called with `slot=None` (or no slot and no dashboard active)
- **THEN** the `/api/spawn` body does NOT include a `parent_session` field, and the response includes `"slot": null`

#### Scenario: slot="bridge" creates shared session and attaches task

- **WHEN** `dispatch` is called with `slot="bridge"` (or defaulted to bridge via dashboard_port)
- **THEN** the system calls `POST /api/chat/slots {"name": "bridge"}` (409 treated as success), sends `/api/spawn` with `parent_session="dashboard:bridge"`, and the response includes `"slot": "bridge"`

#### Scenario: slot=True creates a dedicated session per task

- **WHEN** `dispatch` is called with `slot=True`
- **THEN** the system generates a unique 8-hex suffix, calls `POST /api/chat/slots {"name": "<suffix>"}`, sends `/api/spawn` with `parent_session="dashboard:<suffix>"`, and the response includes `"slot": "<suffix>"`

#### Scenario: slot="<name>" creates or reuses a named session

- **WHEN** `dispatch` is called with `slot="my-review"`
- **THEN** the system calls `POST /api/chat/slots {"name": "my-review"}` (409 treated as success), sends `/api/spawn` with `parent_session="dashboard:my-review"`, and the response includes `"slot": "my-review"`

#### Scenario: Two dispatches with the same slot name share one session

- **WHEN** two `dispatch` calls are made with `slot="review-trn-147"`
- **THEN** both tasks have `parent_session="dashboard:review-trn-147"` on `/api/spawn`, and both completions appear in the same dashboard session

#### Scenario: Crew default inferred from dashboard_port at dispatch time

- **WHEN** a crew has `dashboard_port` set and `dispatch` is called with no explicit `slot`
- **THEN** the effective slot is `"bridge"` (self-corrects when dashboard is toggled)

#### Scenario: Crew default is null when no dashboard

- **WHEN** a crew has no `dashboard_port` and `dispatch` is called with no explicit `slot`
- **THEN** the effective slot is null (headless)

### Requirement: dispatch accepts tasks list as an alternative overload

The `dispatch` tool SHALL accept `tasks: list[str]` as an alternative to `task: str`. The two parameters SHALL be mutually exclusive. When `tasks` is provided, all dispatch semantics apply identically to each task in the list. All tasks in one batch share the same `agent`, `model`, `slot`, and `crew_id`.

The `slot` parameter SHALL apply uniformly across all tasks in a batch. For `slot=True`, each task in the batch receives its own unique slot name. For a string slot, all tasks in the batch share the same slot.

See `specs/batch-dispatch/spec.md` for the full batch dispatch contract.

#### Scenario: Batch dispatch uses same validation as single dispatch

- **WHEN** `dispatch` is called with `tasks=[...]` and an agent not on the six-persona roster
- **THEN** the system returns a validation error without dispatching any task

#### Scenario: Batch dispatch records last_task_at per task

- **WHEN** `dispatch` is called with `tasks=[...]` and all `/api/spawn` calls succeed
- **THEN** the transport updates `last_task_at` in the crew registry for each successfully dispatched task

#### Scenario: Batch dispatch with slot=True gives each task its own slot

- **WHEN** `dispatch` is called with `tasks=[...]` and `slot=True`
- **THEN** each task is sent with a distinct `parent_session="dashboard:<unique-suffix>"`

#### Scenario: Batch dispatch with named slot shares one session for all tasks

- **WHEN** `dispatch` is called with `tasks=[...]` and `slot="my-batch"`
- **THEN** every task is sent with `parent_session="dashboard:my-batch"`

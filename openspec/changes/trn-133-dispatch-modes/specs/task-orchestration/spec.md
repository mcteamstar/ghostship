# Task Orchestration — Delta Spec (trn-133-dispatch-modes)

Updates to the `task-orchestration` capability.

## MODIFIED Requirements

### Requirement: Task dispatch

The system SHALL dispatch a task to a named agent persona within a specified crew and return a task ID for later tracking. Every dispatched task SHALL be a dedicated (retained) run at the crew gateway, not a default shared run, so that a later forceful stop of that task cannot destroy session data shared with another task.

The system SHALL accept an optional `dispatch_mode` parameter on `dispatch()` with one of three values:

- `"none"` (default when the crew has no dashboard) — no `parent_session` is set on `/api/spawn`. Current behaviour, zero regression.
- `"shared"` (default when the crew was launched with `dashboard=True`) — every task dispatched to the crew attaches to a single shared dashboard slot by passing `parent_session="dashboard:<crew-id>"` on `/api/spawn`.
- `"unique"` — each dispatched task attaches to its own named dashboard slot by passing `parent_session="dashboard:<crew-id>-<task-id>"` on `/api/spawn`.

When `dispatch_mode` is not explicitly provided, the system SHALL use the crew's `dispatch_mode_default` from the registry (set at launch time: `"shared"` if `dashboard=True`, `"none"` otherwise).

The effective `dispatch_mode` SHALL be echoed back in the `dispatch()` response.

#### Scenario: Dispatch to an existing crew

- **WHEN** `dispatch` is called with a `task`, an `agent` (defaulting to `ghost`), and a `crew_id` that exists
- **THEN** the system ensures the crew container is running, forwards the task to the crew's `/api/spawn` endpoint with a dedicated-run request, and returns a `task_id` with status `dispatched`, `created_at` as an ISO 8601 UTC timestamp, and `dispatch_mode` echoing the effective mode

#### Scenario: Dispatch without crew_id when crews exist

- **WHEN** `dispatch` is called without `crew_id` and one or more crews are registered
- **THEN** the system returns an error listing the live crew IDs instead of guessing which crew to use

#### Scenario: Dispatch when no crews exist

- **WHEN** `dispatch` is called without `crew_id` and no crews are registered
- **THEN** the system returns an error instructing the caller to call `launch` first

#### Scenario: dispatch_mode=shared attaches task to crew slot

- **WHEN** `dispatch` is called with `dispatch_mode="shared"` (or defaulted to shared via the crew's registry flag)
- **THEN** the `/api/spawn` body includes `parent_session="dashboard:<crew-id>"` and the response includes `"dispatch_mode": "shared"`

#### Scenario: dispatch_mode=unique attaches each task to its own slot

- **WHEN** `dispatch` is called with `dispatch_mode="unique"`
- **THEN** the `/api/spawn` body includes `parent_session="dashboard:<crew-id>-<task-id>"` where `<task-id>` is the ID returned by the gateway, and the response includes `"dispatch_mode": "unique"`

#### Scenario: dispatch_mode=none sends no parent_session

- **WHEN** `dispatch` is called with `dispatch_mode="none"` (or the crew's default is none)
- **THEN** the `/api/spawn` body does NOT include a `parent_session` field, and the response includes `"dispatch_mode": "none"`

#### Scenario: dispatch_mode invalid value rejected

- **WHEN** `dispatch` is called with `dispatch_mode` set to any value other than `"none"`, `"shared"`, or `"unique"`
- **THEN** the system returns a validation error before dispatching any task

#### Scenario: Crew default inferred from dashboard flag at launch

- **WHEN** a crew is launched with `dashboard=True` and `dispatch` is called with no explicit `dispatch_mode`
- **THEN** the effective mode is `"shared"` (inherited from `dispatch_mode_default="shared"` in the registry)

#### Scenario: Crew default is none when dashboard was not enabled

- **WHEN** a crew is launched with `dashboard=False` (the default) and `dispatch` is called with no explicit `dispatch_mode`
- **THEN** the effective mode is `"none"` (inherited from `dispatch_mode_default="none"` in the registry)

### Requirement: dispatch accepts tasks list as an alternative overload

The `dispatch` tool SHALL accept `tasks: list[str]` as an alternative to `task: str`. The two parameters SHALL be mutually exclusive. When `tasks` is provided, all dispatch semantics (agent validation, model validation, crew lookup, `_ensure_crew_running`) apply identically to each task in the list before any `/api/spawn` call is made. All tasks in one batch share the same `agent`, `model`, `crew_id`, and `dispatch_mode`.

The `dispatch_mode` parameter SHALL apply uniformly across all tasks in a batch. For `"unique"` mode, each task in the batch receives its own `parent_session` keyed to its individual `task_id`.

See `specs/batch-dispatch/spec.md` for the full batch dispatch contract, registry record, and error scenarios.

#### Scenario: Batch dispatch uses same validation as single dispatch

- **WHEN** `dispatch` is called with `tasks=[...]` and an agent not on the six-persona roster
- **THEN** the system returns a validation error without dispatching any task — identical behaviour to `dispatch(task=..., agent="invalid")`

#### Scenario: Batch dispatch records last_task_at per task

- **WHEN** `dispatch` is called with `tasks=[...]` and all `/api/spawn` calls succeed
- **THEN** the transport updates `last_task_at` in the crew registry for each successfully dispatched task, using the timestamp of that task's `/api/spawn` response

#### Scenario: Batch dispatch with shared mode uses one parent_session for all tasks

- **WHEN** `dispatch` is called with `tasks=[...]` and `dispatch_mode="shared"`
- **THEN** every task in the batch is sent to `/api/spawn` with the same `parent_session="dashboard:<crew-id>"`

#### Scenario: Batch dispatch with unique mode gives each task its own parent_session

- **WHEN** `dispatch` is called with `tasks=[...]` and `dispatch_mode="unique"`
- **THEN** each task is sent with `parent_session="dashboard:<crew-id>-<task-id>"` where `<task-id>` is that task's gateway-assigned ID

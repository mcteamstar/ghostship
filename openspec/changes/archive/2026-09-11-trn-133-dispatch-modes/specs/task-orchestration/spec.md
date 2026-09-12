# Task Orchestration — Delta Spec (trn-133-dispatch-modes)

Updates to the `task-orchestration` capability.

## MODIFIED Requirements

### Requirement: Task dispatch

The system SHALL dispatch a task to a named agent persona within a specified crew and return a task ID for later tracking. Every dispatched task SHALL be a dedicated (retained) run at the crew gateway, not a default shared run, so that a later forceful stop of that task cannot destroy session data shared with another task.

The system SHALL accept an optional `mode` parameter on `dispatch()` with one of three values:

- `"headless"` (default when the crew has no dashboard) — no `parent_session` is set on `/api/spawn`. Current behaviour, zero regression.
- `"anchored"` (default when the crew was launched with `dashboard=True`) — every task dispatched to the crew attaches to a single shared dashboard slot by passing `parent_session="dashboard:<crew-id>"` on `/api/spawn`.
- `"free"` — each dispatched task attaches to its own named dashboard slot by passing `parent_session="dashboard:<crew-id>-<8hex>"` on `/api/spawn`, where `<8hex>` is a transport-generated `uuid4().hex[:8]` suffix chosen before the `/api/spawn` call.

When `mode` is not explicitly provided, the system SHALL use the crew's `mode_default` from the registry (set at launch time: `"anchored"` if `dashboard=True`, `"headless"` otherwise).

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

#### Scenario: mode=anchored attaches task to crew slot

- **WHEN** `dispatch` is called with `mode="anchored"` (or defaulted to shared via the crew's registry flag)
- **THEN** the `/api/spawn` body includes `parent_session="dashboard:<crew-id>"` and the response includes `"mode": "anchored"`

#### Scenario: mode=free attaches each task to its own slot

- **WHEN** `dispatch` is called with `mode="free"`
- **THEN** the `/api/spawn` body includes `parent_session="dashboard:<crew-id>-<8hex>"` where `<8hex>` is a transport-generated `uuid4().hex[:8]` suffix chosen before the call (revised D3), and the response includes `"mode": "free"` and `"parent_session"` echoing the slot name

#### Scenario: mode=headless sends no parent_session

- **WHEN** `dispatch` is called with `mode="headless"` (or the crew's default is headless)
- **THEN** the `/api/spawn` body does NOT include a `parent_session` field, and the response includes `"mode": "headless"`

#### Scenario: mode invalid value rejected

- **WHEN** `dispatch` is called with `mode` set to any value other than `"headless"`, `"anchored"`, or `"free"`
- **THEN** the system returns a validation error before dispatching any task

#### Scenario: Crew default inferred from dashboard flag at launch

- **WHEN** a crew is launched with `dashboard=True` and `dispatch` is called with no explicit `mode`
- **THEN** the effective mode is `"anchored"` (inherited from `mode_default="anchored"` in the registry)

#### Scenario: Crew default is none when dashboard was not enabled

- **WHEN** a crew is launched with `dashboard=False` (the default) and `dispatch` is called with no explicit `mode`
- **THEN** the effective mode is `"headless"` (inherited from `mode_default="headless"` in the registry)

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

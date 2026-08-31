## ADDED Requirements

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

The `schedule` tool SHALL accept an optional `model` string parameter, for `cron`, `interval`, and `delay` (one-shot) job creation alike. When provided, it SHALL be forwarded as `model` in the `/api/crons` request body, pinning that one recurring or one-shot job's model. The same validation and precedence rules as the `dispatch` tool's `model` parameter apply.

#### Scenario: Schedule with a model override
- **WHEN** `schedule(interval=300, message="...", agent="ghost", crew_id="my-crew", model="claude-sonnet-5")` is called
- **THEN** the system forwards `model: "claude-sonnet-5"` in the `/api/crons` request body when creating the job

#### Scenario: Schedule with a model override on a one-shot delay job
- **WHEN** `schedule(delay=300, message="...", agent="ghost", crew_id="my-crew", model="claude-sonnet-5")` is called
- **THEN** the system forwards `model: "claude-sonnet-5"` in the one-shot job's `/api/crons` request body, the same as the `cron`/`interval` path

#### Scenario: Schedule without a model override
- **WHEN** `schedule` is called without a `model` parameter
- **THEN** the system omits `model` from the `/api/crons` request body, leaving persona/env-var model precedence unchanged

### Requirement: Captain standing-orders check-in supports model override

The `captain(action="order")` call SHALL accept an optional `model` string parameter, forwarded as `model` in the `/api/crons` request body when a new standing-orders check-in job is created. The parameter SHALL be ignored (with no error) when resuming a previously paused check-in, since no new job is created in that path.

#### Scenario: Captain order with a model override on a new check-in
- **WHEN** `captain(crew_id="my-crew", action="order", template="sdd", change_name="...", interval=300, model="claude-opus-5")` creates a new check-in job
- **THEN** the system forwards `model: "claude-opus-5"` in the `/api/crons` request body for that job

#### Scenario: Captain order with a model override on a resumed check-in
- **WHEN** `captain(action="order", model="claude-opus-5")` is called to resume a previously paused check-in
- **THEN** the system resumes the existing job unchanged and does not apply the `model` parameter, since no new job is created

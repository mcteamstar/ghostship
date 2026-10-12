# captain Specification

## Purpose

Defines the behaviour of the `captain` MCP tool — the control interface for managing the crew's persistent check-in schedule, including how stop operations interact with the gateway cron and the ghostship schedule registry.

## Requirements

### Requirement: RAVEN_SELF_CANCEL uses transport endpoint, not KiroCrew CLI

The `{{RAVEN_SELF_CANCEL}}` placeholder SHALL resolve to an instruction that calls
`POST /crews/{crew_id}/captain/stop` on the transport REST API via curl, authenticated
with the dashboard session cookie. It SHALL NOT instruct Raven to use `kirocrew cron
pause` — the captain schedule is registered in the transport's schedule registry and is
not visible inside the crew container via `kirocrew cron list`.

The transport SHALL expose `POST /crews/{crew_id}/captain/stop` as a crew-internal
endpoint that stops the captain schedule entry for the named crew. The request SHALL be
authenticated via the dashboard session cookie (`Cookie: mc_token_{port}=<value>`),
the same credential path used for spawn calls from inside the crew. The endpoint SHALL:

1. Look up the captain schedule entry in the transport registry for `crew_id`.
2. Disable it (set `enabled: false`) — the same operation as `captain(action="stop")`.
3. Return `{"status": "stopped"}` on success.
4. Return `404` with a JSON error body if no captain entry exists for this crew.
5. Return `400` if the entry exists but is already stopped.

The endpoint SHALL be reachable from inside the crew container at
`http://localhost:{transport_port}/crews/{crew_id}/captain/stop`, where
`{transport_port}` is the transport's port as exposed inside the container (64057).
The crew_id is available to the agent as `$KIROCREW_CREW_ID`.

#### Scenario: Raven self-cancels via transport endpoint on SDD completion
- **WHEN** Raven determines the standing orders are met and calls
  `POST /crews/{crew_id}/captain/stop` with the dashboard cookie
- **THEN** the transport disables the captain schedule entry for that crew
- **AND** returns `{"status": "stopped"}`
- **AND** subsequent captain monitor ticks do not fire a new Raven check-in

#### Scenario: Endpoint returns 404 when no captain entry exists
- **WHEN** `POST /crews/{crew_id}/captain/stop` is called for a crew with no captain entry
- **THEN** the transport returns HTTP 404 with a JSON error body

#### Scenario: Endpoint returns 400 when captain is already stopped
- **WHEN** `POST /crews/{crew_id}/captain/stop` is called and the captain entry is
  already disabled
- **THEN** the transport returns HTTP 400 indicating the captain is already stopped

#### Scenario: Endpoint requires dashboard cookie auth
- **WHEN** `POST /crews/{crew_id}/captain/stop` is called without a valid dashboard cookie
- **THEN** the transport returns HTTP 401 or HTTP 403

### Requirement: captain stop always disables the schedule registry entry

When `captain(action="stop")` is called, the ghostship schedule registry entry for the captain check-in job SHALL be updated to `enabled: false` unconditionally — regardless of the job's current state in the KiroCrew gateway. The registry update SHALL NOT be skipped when the gateway already reports the job as disabled.

#### Scenario: captain stop when gateway cron is already disabled

- **WHEN** `captain(action="stop")` is called and the captain check-in job's gateway cron is already `enabled: false` (e.g. Raven paused it via CLI)
- **THEN** the ghostship registry entry is updated to `enabled: false`
- **THEN** the crew is eligible for idle-stop — the gateway already shows `enabled: false`, so the idle monitor's `_cron_has_enabled_job` check passes and the crew stops after `GA_IDLE_TIMEOUT_SECS` with no other activity

#### Scenario: captain stop when gateway cron is enabled

- **WHEN** `captain(action="stop")` is called and the captain check-in job's gateway cron is `enabled: true`
- **THEN** the transport calls the gateway cron disable API AND updates the registry to `enabled: false`
- **THEN** the crew is eligible for idle-stop after `GA_IDLE_TIMEOUT_SECS` with no other activity

### Requirement: Configurable user-defined orders directory

The system SHALL support a `GA_ORDERS_DIR` environment variable that points to an operator-managed directory of additional standing-order template files. When set and the directory exists, its `.md` files SHALL be merged with the built-in `academy/orders/` templates to form the effective template set. A user-defined template whose filename stem matches a built-in template name SHALL override (take precedence over) the built-in template. Built-in templates with no user-defined counterpart remain available unchanged.

When `GA_ORDERS_DIR` is unset or its path does not exist, the system SHALL behave exactly as before, using only the built-in `academy/orders/` templates.

#### Scenario: GA_ORDERS_DIR adds new templates
- **WHEN** `GA_ORDERS_DIR` points to a directory containing `deploy.md` and `audit.md`
- **THEN** `captain(action="order", template="deploy")` and `captain(action="order", template="audit")` are accepted, and the templates are resolved from the user-defined directory

#### Scenario: User-defined template overrides a built-in
- **WHEN** `GA_ORDERS_DIR` points to a directory containing `sdd.md`
- **THEN** `captain(action="order", template="sdd")` resolves the user-defined `sdd.md` instead of the built-in `academy/orders/sdd.md`

#### Scenario: GA_ORDERS_DIR unset — behaviour unchanged
- **WHEN** `GA_ORDERS_DIR` is not set
- **THEN** only the built-in `academy/orders/` templates are available, and all existing captain behaviour is preserved

#### Scenario: GA_ORDERS_DIR path does not exist
- **WHEN** `GA_ORDERS_DIR` is set to a path that does not exist on the filesystem
- **THEN** the system logs a warning and falls back to built-in templates only — no error is raised at transport startup or at template load time

#### Scenario: Built-in templates remain available when GA_ORDERS_DIR is set
- **WHEN** `GA_ORDERS_DIR` is set and does NOT contain a file named `independent-review.md`
- **THEN** `captain(action="order", template="independent-review")` still resolves the built-in template from `academy/orders/`

### Requirement: Captain dispatch uses a compatible model on Claude-backend crews

When the system dispatches a Captain check-in on a crew whose configured
`acp_backend` is `"claude"` (or whose crew-level default model is a Claude model),
and no explicit model override is provided by the Captain order, the system SHALL
derive the dispatch model from the crew's configured default model rather than
relying on the `raven.json` `"model"` field. This ensures Raven is always dispatched
on a model that is compatible with the backend's capabilities.

The `raven.json` `"model"` field is a default for non-Claude backend crews; it SHALL
NOT be used as the dispatch model when the crew runs on a Claude backend.

#### Scenario: Captain check-in on Claude-backend crew uses crew model

- **WHEN** `_dispatch_captain_checkin` is called for a crew with `acp_backend="claude"`
  and the caller passes `model=None`
- **THEN** the spawn request includes `"model": <crew_default_model>` derived from the
  crew's registry entry, not a GPT model string from `raven.json`

#### Scenario: Explicit model override is respected

- **WHEN** `_dispatch_captain_checkin` is called with an explicit non-None `model`
  parameter
- **THEN** the spawn request uses that explicit model, regardless of the crew's
  configured backend or default model

#### Scenario: Non-Claude crew unaffected

- **WHEN** `_dispatch_captain_checkin` is called for a crew that does not use the
  Claude backend, with `model=None`
- **THEN** the spawn request is built exactly as before (no `"model"` key from the
  crew registry is added; gateway picks the default)

### Requirement: Captain check-in dispatch is skipped under host memory pressure

When the host is under critical memory pressure, the transport SHALL skip the
`POST /api/spawn` call for a captain check-in and defer to the next scheduled
cron tick rather than making a doomed request that the gateway will refuse.

The skip SHALL NOT advance `current_task_id` or `next_fire_at`. The
`immediate_dispatch_error` field in the check-in result SHALL be set to a
string beginning with the stable marker `memory_pressure:`, with the
available and threshold GB values included for observability.

The check SHALL fail-open: when the memory probe is unavailable (returns no
value or raises), the transport SHALL proceed with the dispatch unconditionally
so that a probe outage does not freeze the crew's check-in schedule.

#### Scenario: Check-in skipped when host memory is below critical threshold
- **WHEN** `_dispatch_captain_checkin` is called and the host available memory is below `GA_RESOURCE_CRITICAL_GB`
- **THEN** the transport SHALL NOT call `POST /api/spawn`
- **THEN** `immediate_dispatch_error` SHALL be set to a string beginning with `memory_pressure:`
- **THEN** `current_task_id` SHALL NOT be updated
- **THEN** `next_fire_at` SHALL NOT be advanced

#### Scenario: Check-in proceeds when host memory is at or above critical threshold
- **WHEN** `_dispatch_captain_checkin` is called and the host available memory is at or above `GA_RESOURCE_CRITICAL_GB`
- **THEN** the transport SHALL call `POST /api/spawn` as normal

#### Scenario: Check-in proceeds when memory probe is unavailable (fail-open)
- **WHEN** `_dispatch_captain_checkin` is called and the memory probe helper returns no value or raises
- **THEN** the transport SHALL proceed with `POST /api/spawn` unconditionally

### Requirement: Captain check-in tracks and escalates sustained memory pressure

The transport SHALL maintain a `consecutive_memory_pressure_skips` counter on
the captain schedule entry. Each memory-pressure skip or gateway memory-pressure
refusal SHALL increment the counter. A successful dispatch SHALL reset it to `0`.

When the counter reaches `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` (default `3`),
the transport SHALL send exactly one escalation mail to `admiral@localhost` with
subject `captain check-in deferred — sustained memory pressure <crew_id>`. The
escalation is edge-triggered: once emitted at the boundary, the transport SHALL
NOT re-emit on subsequent cycles while the counter remains at or above the bound.

#### Scenario: Escalation sent exactly once when sustained pressure threshold is crossed
- **WHEN** `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` is `3` and the third consecutive memory-pressure skip or refusal is recorded for a crew
- **THEN** exactly one mail is sent to `admiral@localhost` with subject `captain check-in deferred — sustained memory pressure <crew_id>`

#### Scenario: No re-escalation while pressure persists above the bound
- **WHEN** more than `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` consecutive memory-pressure skips have occurred for a crew
- **THEN** no additional escalation mail is sent (edge-triggered, not level-triggered)

#### Scenario: Counter reset on successful dispatch
- **WHEN** `_dispatch_captain_checkin` succeeds and `current_task_id` is advanced
- **THEN** `consecutive_memory_pressure_skips` is set to `0` for that crew's captain schedule entry

#### Scenario: Missing counter field treated as zero
- **WHEN** a captain schedule registry entry has no `consecutive_memory_pressure_skips` field
- **THEN** the transport treats it as `0` when incrementing

### Requirement: Raven order templates include a memory-pressure refusal branch

The `spec-driven-development.md` and `independent-review.md` captain order
templates SHALL document that a `POST /api/spawn` call MAY be refused by the
gateway under critical host memory pressure.

Each template SHALL instruct Raven to:
- Treat a memory-pressure refusal identically to any other failed spawn: write
  no dispatch confirmation and leave the pending intent marker so the dispatch
  is retried on a later check-in cycle.
- NOT treat a memory-pressure refusal as a completed dispatch.
- NOT retry the refused spawn within the same check-in cycle.
- Count consecutive memory-pressure refused cycles and, after
  `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` consecutive refusals for the same
  dispatch, mail `admiral@localhost` with subject
  `captain check-in deferred — sustained memory pressure <crew_id>`
  (substituting the actual crew id) before holding.

#### Scenario: Raven holds and retries on a memory-pressure refusal
- **WHEN** Raven issues `POST /api/spawn` and receives a memory-pressure refusal (HTTP 503 or 429 whose body names memory pressure)
- **THEN** Raven writes no dispatch confirmation and leaves the pending intent marker active
- **THEN** Raven does NOT treat the cycle as a completed dispatch

#### Scenario: Raven escalates after sustained memory-pressure refusals
- **WHEN** Raven has observed `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` consecutive memory-pressure refusals for the same dispatch intent
- **THEN** Raven mails `admiral@localhost` with subject `captain check-in deferred — sustained memory pressure <crew_id>` (substituting the actual crew id)
- **THEN** Raven holds and does not attempt another spawn in the same cycle

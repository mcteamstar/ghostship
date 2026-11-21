# captain Specification

## Purpose

Defines the behaviour of the `captain` MCP tool — the control interface for managing the crew's persistent check-in schedule, including how stop operations interact with the gateway cron and the ghostship schedule registry.

## Requirements

### Requirement: captain tool description lists free-will as a built-in template

The `captain` MCP tool description SHALL list `free-will` / `free` / `willy` as a
built-in template alongside `spec-driven-development` / `sdd` / `specky` and
`independent-review` / `indy`.

#### Scenario: captain tool docstring includes free-will
- **WHEN** the `captain` tool description is read (e.g. via `/openapi.json` or the
  MCP tool listing)
- **THEN** the text includes `free-will` and its aliases `free` and `willy`
- **THEN** the description explains that `free-will` is the open-ended autonomous
  template

### Requirement: Raven self-cancels through the transport

The `{{RAVEN_SELF_CANCEL}}` instruction SHALL call the transport stop endpoint with dashboard-cookie authentication; it SHALL NOT use `kirocrew cron pause`, which cannot see the transport schedule registry.

#### Scenario: Raven self-cancels via transport endpoint on SDD completion
- **WHEN** Raven determines the standing orders are met and calls
  `POST /crews/{crew_id}/captain/stop` with the dashboard cookie
- **THEN** the transport disables the captain schedule entry for that crew
- **AND** returns `{"status": "stopped"}`
- **AND** subsequent captain monitor ticks do not fire a new Raven check-in

#### Scenario: Stop endpoint is reachable from inside the crew
- **WHEN** Raven self-cancels in a crew with `KIROCREW_CREW_ID` set
- **THEN** the template calls `http://localhost:{transport_port}/crews/{crew_id}/captain/stop` using the transport port exposed inside the container (default 64057)

### Requirement: Transport stop endpoint disables the Captain schedule

The crew-internal stop endpoint SHALL authenticate with the dashboard session cookie (`Cookie: mc_token_{port}=<value>`), the same credential path used for spawn calls; it SHALL disable the registry schedule, return `status: stopped` on success, 404 when absent, and 400 when already stopped.

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

### Requirement: User orders directory adds templates

When `GA_ORDERS_DIR` names an existing directory, its `.md` templates SHALL be merged with built-in `academy/orders/` templates; built-in templates without an override SHALL remain available.

#### Scenario: GA_ORDERS_DIR adds new templates
- **WHEN** `GA_ORDERS_DIR` points to a directory containing `deploy.md` and `audit.md`
- **THEN** `captain(action="order", template="deploy")` and `captain(action="order", template="audit")` are accepted, and the templates are resolved from the user-defined directory

#### Scenario: Built-in templates remain available when GA_ORDERS_DIR is set
- **WHEN** `GA_ORDERS_DIR` is set and does NOT contain a file named `independent-review.md`
- **THEN** `captain(action="order", template="independent-review")` still resolves the built-in template from `academy/orders/`

### Requirement: User templates override matching built-ins

A user-defined template whose filename stem matches a built-in name SHALL take precedence over that built-in.

#### Scenario: User-defined template overrides a built-in
- **WHEN** `GA_ORDERS_DIR` points to a directory containing `sdd.md`
- **THEN** `captain(action="order", template="sdd")` resolves the user-defined `sdd.md` instead of the built-in `academy/orders/sdd.md`

### Requirement: Missing user orders directory preserves defaults

When `GA_ORDERS_DIR` is unset or its path does not exist, the system SHALL use only built-in `academy/orders/` templates.

#### Scenario: GA_ORDERS_DIR unset — behaviour unchanged
- **WHEN** `GA_ORDERS_DIR` is not set
- **THEN** only the built-in `academy/orders/` templates are available, and all existing captain behaviour is preserved

#### Scenario: GA_ORDERS_DIR path does not exist
- **WHEN** `GA_ORDERS_DIR` is set to a path that does not exist on the filesystem
- **THEN** the system logs a warning and falls back to built-in templates only — no error is raised at transport startup or at template load time

### Requirement: Captain dispatch uses a compatible model on Claude-backend crews

On Claude-backend crews, Captain check-ins SHALL use the crew's configured model unless an explicit order override is set; `raven.json`'s model SHALL apply only to non-Claude crews.

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

### Requirement: Captain check-in defers under critical memory pressure

Under critical host memory pressure, the transport SHALL skip `POST /api/spawn` until the next tick without changing `current_task_id` or `next_fire_at`. The result SHALL report `memory_pressure:` with available and threshold GB values.

#### Scenario: Check-in skipped when host memory is below critical threshold
- **WHEN** `_dispatch_captain_checkin` is called and the host available memory is below `GA_RESOURCE_CRITICAL_GB`
- **THEN** the transport SHALL NOT call `POST /api/spawn`
- **THEN** `immediate_dispatch_error` SHALL be set to a string beginning with `memory_pressure:`
- **THEN** `current_task_id` SHALL NOT be updated
- **THEN** `next_fire_at` SHALL NOT be advanced

#### Scenario: Check-in proceeds when host memory is at or above critical threshold
- **WHEN** `_dispatch_captain_checkin` is called and the host available memory is at or above `GA_RESOURCE_CRITICAL_GB`
- **THEN** the transport SHALL call `POST /api/spawn` as normal

### Requirement: Captain check-in fails open when memory probing is unavailable

If the memory probe returns no value or raises, the transport SHALL proceed with dispatch.

#### Scenario: Check-in proceeds when memory probe is unavailable (fail-open)
- **WHEN** `_dispatch_captain_checkin` is called and the memory probe helper returns no value or raises
- **THEN** the transport SHALL proceed with `POST /api/spawn` unconditionally

### Requirement: Captain schedule tracks consecutive pressure failures

Each memory-pressure skip or gateway refusal SHALL increment `consecutive_memory_pressure_skips`; a successful dispatch SHALL reset it to zero, and a missing field SHALL count as zero.

#### Scenario: Counter reset on successful dispatch
- **WHEN** `_dispatch_captain_checkin` succeeds and `current_task_id` is advanced
- **THEN** `consecutive_memory_pressure_skips` is set to `0` for that crew's captain schedule entry

#### Scenario: Missing counter field treated as zero
- **WHEN** a captain schedule registry entry has no `consecutive_memory_pressure_skips` field
- **THEN** the transport treats it as `0` when incrementing

### Requirement: Captain escalates once after sustained pressure

At `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` consecutive failures (default 3), the transport SHALL send one escalation with subject `captain check-in deferred — sustained memory pressure <crew_id>` and SHALL NOT repeat it until reset.

#### Scenario: Escalation sent exactly once when sustained pressure threshold is crossed
- **WHEN** `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` is `3` and the third consecutive memory-pressure skip or refusal is recorded for a crew
- **THEN** exactly one mail is sent to `admiral@localhost` with subject `captain check-in deferred — sustained memory pressure <crew_id>`

#### Scenario: No re-escalation while pressure persists above the bound
- **WHEN** more than `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` consecutive memory-pressure skips have occurred for a crew
- **THEN** no additional escalation mail is sent (edge-triggered, not level-triggered)

### Requirement: Order templates preserve retry state after memory refusal

The SDD and independent-review templates SHALL treat a memory-pressure refusal as a failed spawn: write no confirmation, keep the pending intent, do not retry in the same cycle, and retry on a later check-in.

#### Scenario: Raven holds and retries on a memory-pressure refusal
- **WHEN** Raven issues `POST /api/spawn` and receives a memory-pressure refusal (HTTP 503 or 429 whose body names memory pressure)
- **THEN** Raven writes no dispatch confirmation and leaves the pending intent marker active
- **THEN** Raven does NOT treat the cycle as a completed dispatch

### Requirement: Order templates escalate sustained memory refusals

Templates SHALL count consecutive memory-pressure refusals and, at the configured threshold, mail the Admiral with the sustained-pressure subject and actual crew ID before holding.

#### Scenario: Raven escalates after sustained memory-pressure refusals
- **WHEN** Raven has observed `GA_SPAWN_PRESSURE_ESCALATE_CYCLES` consecutive memory-pressure refusals for the same dispatch intent
- **THEN** Raven mails `admiral@localhost` with subject `captain check-in deferred — sustained memory pressure <crew_id>` (substituting the actual crew id)
- **THEN** Raven holds and does not attempt another spawn in the same cycle

### Requirement: Cron captain schedule evaluates first fire from cron expression

When `_captain_do_order()` creates a new captain schedule with a cron expression,
the initial `next_fire_at` SHALL be derived by evaluating the cron expression against
the current time, not hardcoded to `now + 60`. Interval-based schedules SHALL
continue to use the 60-second initial delay.

#### Scenario: Cron schedule fires at next cron tick, not 60s
- **WHEN** `captain(action="order", cron="0 9 * * *")` is called at 08:00 UTC
- **THEN** the first `next_fire_at` is the next 09:00 UTC, not 08:01 UTC

#### Scenario: Interval schedule retains 60s initial delay
- **WHEN** `captain(action="order", interval=3600)` is called
- **THEN** the first `next_fire_at` is approximately `now + 60s`

### Requirement: _steer_captain_checkin classifies errors by HTTP status code

Captain SHALL use structured gateway outcomes for continuation. A bare HTTP 400 SHALL NOT trigger another write. A busy outcome SHALL preserve the tracked task ID.

#### Scenario: 400 on /continue path triggers follow-up steer
- **WHEN** continuation returns HTTP 400
- **THEN** Captain starts recovery only if the response confirms a missing session or restore failure; otherwise it surfaces the rejection

#### Scenario: Continuation acceptance is unknown
- **WHEN** Captain cannot establish whether a continuation or replacement spawn was accepted
- **THEN** Captain adopts an existing task ID only when unique correlation identifies that attempt
- **AND** Captain exposes a hold to the operator without replaying the request when correlation is inconclusive

### Requirement: verify_password handles scrypt resource exceptions

`verify_password()` SHALL return `False` (and not raise) when the scrypt hash
verification raises `OSError` (maxmem exceeded) or `OverflowError` (parameter
overflow). These exceptions join the existing `(ValueError, TypeError)` in the
catch clause.

#### Scenario: Extreme scrypt parameters return False, not exception
- **WHEN** a stored hash has extreme `n`/`r`/`p` values that exceed system scrypt limits
- **THEN** `verify_password()` returns `False`
- **THEN** no exception propagates to the caller

### Requirement: Captain paces multiple task starts in a check-in

Captain SHALL default to one task start per check-in. It SHALL start multiple independent tasks only when the standing order authorizes them, admit them sequentially, and reconcile each task identity, intent, and returned ID before the next start. A memory-pressure deferral or uncertain admission SHALL stop further starts for the check-in, with pending work reconciled before a later retry. Admitted tasks can continue in parallel.

#### Scenario: One task is eligible
- **WHEN** an order needs one next task
- **THEN** Captain dispatches that task using the normal intent protocol

#### Scenario: Several tasks are eligible
- **WHEN** an order explicitly authorizes several independent work items
- **THEN** Captain starts each authorized task sequentially and records its confirmed task ID before starting the next
- **AND** earlier admitted tasks can continue in parallel with later starts

#### Scenario: Memory pressure defers a dispatch
- **WHEN** admission defers a start due to memory pressure
- **THEN** Captain stops starting tasks for that check-in and leaves unconfirmed work pending
- **AND** later check-ins reconcile prior intents and task IDs before retrying pending work

#### Scenario: Admission outcome is uncertain
- **WHEN** Captain cannot confirm whether a task start was accepted
- **THEN** Captain stops further starts for that check-in and reconciles the intent and task ID before retrying on a later check-in

### Requirement: Captain recovers from a confirmed Raven session restore failure

Captain SHALL retire the failed Raven task reference and attempt one fresh check-in of the same enabled standing order when continuation reports a confirmed session restore failure.

#### Scenario: Continuation fails after acceptance
- **WHEN** the gateway accepts a continuation and its recorded Raven task later finishes with a confirmed session restore failure
- **THEN** the next eligible check-in retires that task reference and attempts one fresh Raven check-in instead of continuing the failed task

#### Scenario: Continuation immediately reports a restore failure
- **WHEN** the continuation request explicitly reports a confirmed session restore failure
- **THEN** Captain retires the failed task reference and attempts one fresh Raven check-in

#### Scenario: Fresh Raven encounters previously accepted work
- **WHEN** Raven starts after session recovery
- **THEN** it reconciles the standing order, durable progress, mailbox and gateway task list before dispatching more work
- **AND** it does not dispatch a duplicate for an already accepted work item or retry an intent whose outcome is uncertain

#### Scenario: Gateway failure is ambiguous
- **WHEN** the gateway is busy, task status is unavailable, or the error does not confirm a session restore failure
- **THEN** Captain retains its existing handling and does not trigger a fresh check-in under this recovery rule

#### Scenario: Recovery dispatch is deferred
- **WHEN** normal admission controls defer the fresh check-in
- **THEN** Captain leaves the failed reference retired and retries through the enabled schedule

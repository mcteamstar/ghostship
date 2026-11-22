# captain Specification

## Purpose

Defines the behaviour of the `captain` MCP tool — the control interface for managing the crew's persistent check-in schedule, including how stop operations interact with the gateway cron and the ghostship schedule registry.

## Requirements

### Requirement: One Captain check-in per crew

The system SHALL represent a crew's Captain only as one recurring Raven check-in, with no alternate Captain mechanism.

#### Scenario: Admiral stops the Captain
- **WHEN** `captain(crew_id, action="stop")` is called for a crew with a standing-orders check-in loop running
- **THEN** the system pauses the recurring check-in job without deleting it; any persona task already dispatched and running is left to finish on its own, and the mailbox and job history are left as-is for a future `order` to resume from

### Requirement: Captain exposes an explicit action contract

The MCP tool SHALL accept `captain(crew_id, action, message=None, template=None, change_name=None, cron=None, interval=None)`, with actions `order`, `stop`, or `status`. `order` SHALL require exactly one of `message` or `template`; `change_name` only substitutes a template value.

#### Scenario: Ordering with both or neither message and template
- **WHEN** `captain(crew_id, action="order", ...)` is called with both `message` and `template` set, or with neither set
- **THEN** the system returns an error and takes no action

### Requirement: Captain status surfaces both mail directions
The system SHALL make `captain(crew_id, action="status")` report unread-message counts for both directions of Captain communication: the existing `unread_mail` field SHALL count the crew's `captain@localhost` standing-order mailbox, and a separate `unread_admiral_mail` field SHALL count the `admiral@localhost` escalation mailbox. The response SHALL identify both mailbox addresses explicitly. This is a pull/fetch-only status surface; it SHALL NOT add a push notification or live-alert mechanism.

#### Scenario: Captain status reports orders and escalations
- **WHEN** `captain(crew_id, action="status")` is called for a crew with unread orders, unread escalations, or both
- **THEN** the response reports the count for `captain@localhost` and the count for `admiral@localhost` separately, including zero when either mailbox is empty or absent

### Requirement: Captain orders are stored as mail

For `action="order"`, the transport SHALL write a formatted message to the crew's `captain@localhost` mailbox from outside the crew; the mailbox SHALL be the sole record of standing orders.

#### Scenario: First standing order for a crew
- **WHEN** `captain(crew_id, action="order", message=<text>, interval=<n>)` (or `cron=<expr>`) is called for a crew with no existing check-in job
- **THEN** the system writes `<text>` as mail to `captain@localhost` inside the crew, creates a recurring job dispatching `raven` on the given schedule, and returns the new job's identifier

#### Scenario: Updated standing order for a crew already checking in
- **WHEN** `captain(crew_id, action="order", message=<text>)` is called for a crew with an existing, enabled check-in job
- **THEN** the system writes `<text>` as a new mail message to `captain@localhost`, leaves the existing job's schedule and identifier unchanged, and does not require `interval`/`cron` to be repeated

### Requirement: Ordering ensures a recurring Raven check-in

An order SHALL ensure a Raven check-in job exists, creating it only when absent and preserving an existing schedule.

#### Scenario: A schedule is required only when no check-in job exists yet
- **WHEN** `captain(crew_id, action="order", message=<text>)` is called for a crew with no existing check-in job, and neither `interval` nor `cron` is given
- **THEN** the system returns an error and writes no mail, since a brand-new check-in loop has nothing to schedule against

### Requirement: Raven evaluates orders on each check-in

Each recurring check-in SHALL dispatch Raven to assess current crew state against all standing orders and take one action within its authority: dispatch a sanctioned persona, steer an in-flight task, hold, or escalate to the Admiral.

#### Scenario: Raven dispatches the next step
- **WHEN** a check-in finds standing orders not yet met and a clear next atomic step within its authority
- **THEN** Raven dispatches one of the five sanctioned personas for that step via an authenticated `POST` to the crew gateway's own `/api/spawn`, without any ghostship transport code parsing or re-issuing that dispatch

#### Scenario: Raven steers an in-flight worker instead of waiting
- **WHEN** new standing orders arrive while a previously-dispatched persona task is still running
- **THEN** Raven sends the new context to that running task via an authenticated `POST` to the gateway's `/api/spawn/{task_id}/steer`, rather than holding until the task finishes and addressing the new orders only on a later cycle

#### Scenario: Raven holds
- **WHEN** a check-in finds no new orders and no outstanding work needing action
- **THEN** Raven takes no dispatching action that cycle, and the job's next firing proceeds on its existing schedule

#### Scenario: Raven escalates instead of guessing
- **WHEN** a check-in encounters a decision or a permission that is outside Raven's own authority to resolve
- **THEN** Raven sends a message to the Admiral's address rather than guessing or unilaterally proceeding, and continues to hold on that point until a reply arrives in a later check-in

#### Scenario: Raven cannot be steered by the Admiral
- **WHEN** an Admiral wants to change a standing-orders crew's direction
- **THEN** the only supported channel is a further `captain(action="order", ...)` call — `steer` has no applicable `task_id` for a check-in job, since it is a recurring `schedule` resource, not a `dispatch`-created task; this is unrelated to Raven's own ability to steer the persona tasks it dispatches

#### Scenario: Each check-in reassesses the standing orders
- **WHEN** a recurring Captain check-in fires for a crew with standing orders
- **THEN** Raven reads orders since the prior check-in, assesses the crew's current state against the orders as a whole, and uses the job's persistent session for continuity whether the orders came from a template or free-form message

### Requirement: Raven prevents duplicate persona dispatch

Before dispatch, Raven SHALL check pending and confirmed mailbox intents, matching task descriptions, then the asynchronously populated agent field, in that order. It SHALL write a unique pending intent before spawning, confirm the returned task ID after success, and hold or elect one intent when a signal indicates overlap.

#### Scenario: Raven records an intent before spawning when the gateway ID is not yet known
- **WHEN** Raven determines a persona dispatch is needed and all three layers report clear
- **THEN** Raven generates a unique local `intent_id`, prefixes the worker task description with `SDD dispatch <intent_id> <change> <persona>`, writes `dispatching <persona> <intent_id>` to `raven@localhost` BEFORE calling `/api/spawn`, and does not invent the gateway's future task ID

#### Scenario: Raven confirms the server-assigned ID after spawning
- **WHEN** the authenticated `/api/spawn` call succeeds and returns `spawn_task_id`
- **THEN** Raven writes a confirmation to `raven@localhost` with subject `dispatching <persona> <spawn_task_id>` and links it to the pre-spawn `intent_id` in the body

#### Scenario: Subsequent check-in finds a pending dispatch-intent
- **WHEN** a Raven check-in scans `raven@localhost` and finds `dispatching ghost abc123` as an unconfirmed pending intent with no completed confirmation check yet
- **THEN** Raven treats Ghost as already dispatched and holds, even if `kirocrew spawn list` shows no `agent: ghost` entry (due to async population lag)

#### Scenario: Layered check prevents duplicate dispatch on async agent-field lag
- **WHEN** two Raven check-ins fire in close succession after a long-running task completes, and the `agent` field on spawn-list entries is still empty for the new dispatch
- **THEN** the pending/confirmed mailbox signal or the stable task-description signal prevents the second check-in from dispatching a duplicate, even though the agent-field signal alone would have permitted it

#### Scenario: Overlapping check-ins elect one pending marker
- **WHEN** two check-ins write unconfirmed pending intents for the same persona before either has spawned
- **THEN** the check-in with the oldest Maildir arrival/`Date` (then `Message-ID` for a tie) proceeds and the other holds, so at most one `/api/spawn` call is made for that persona

#### Scenario: Pending intent with no spawn is stale after confirmation check
- **WHEN** a pending intent has survived one full subsequent check-in and `kirocrew spawn list` has no task carrying its intent token and no matching worker in flight
- **THEN** Raven treats that pending intent as stale and may retry if the standing order still requires the dispatch

#### Scenario: Confirmed intent with completed task is stale
- **WHEN** a Raven check-in finds `dispatching ghost abc123` as a confirmed intent AND `kirocrew spawn list` shows task `abc123` as completed or the task no longer appears
- **THEN** Raven treats that confirmed intent as stale/resolved and does not hold on its account — the persona may be dispatched again if orders require it

#### Scenario: All three signals clear — dispatch proceeds
- **WHEN** Raven finds no active pending or confirmed intent for the target persona, no matching task description in `kirocrew spawn list`, and no matching agent field
- **THEN** Raven writes a new tokenized pending intent, elects it if necessary, and only then proceeds with the authenticated dispatch

### Requirement: Persona mailboxes provide supplemental crew context

Raven SHOULD read the five sanctioned personas' mailboxes as context, but SHALL use `spawn list` to establish whether work has completed.

#### Scenario: Raven skims persona mailboxes for context
- **WHEN** a check-in assesses the crew's current state
- **THEN** Raven reads each of the five sanctioned personas' own mailboxes directly, in addition to `kirocrew spawn list`/`cron list`, and treats what it finds there as supplementary context rather than a substitute for confirming task completion via `spawn list`

### Requirement: Raven uses the CLI and gateway API for distinct operations

Dispatched sessions SHALL expose no native subagent-control MCP surface. Raven SHALL use `kirocrew` for task and cron listing or pause/resume, and authenticated gateway REST for named dispatch, task detail, steering, or continuation; the IPC credential SHALL be used only in `X-Internal-Secret` and never reported.

#### Scenario: Raven checks status via the CLI, not a credential
- **WHEN** a check-in needs to know whether previously-spawned work has finished, or the state of its own check-in job
- **THEN** Raven runs `kirocrew spawn list` and `kirocrew cron list` — commands that authenticate themselves — and never reads or passes the gateway's IPC credential for these routine checks

#### Scenario: The gateway credential never appears in anything Raven reports
- **WHEN** Raven reads the gateway's local IPC credential file to authenticate a REST call
- **THEN** its actual value never appears in Raven's commentary, reasoning text, task result, or any `pickup`/`bridge`/radio report — it is piped directly from the file into the request header and nowhere else

#### Scenario: CLI and gateway REST divide routine and task control
- **WHEN** Raven needs routine task or cron state, or needs per-task detail or to continue finished work
- **THEN** it uses authenticated `kirocrew` CLI commands for task and cron listing or pause/resume, and the crew gateway REST API for per-task detail and continuation, with the IPC credential passed only in `X-Internal-Secret`

### Requirement: Raven prompts use ghostship-spawn for gateway work

Every Raven prompt source SHALL direct named dispatch, task detail, steering, and continuation through `ghostship-spawn`, not hand-built REST calls, and SHALL omit gateway secrets, cookie paths, and curl data-file arguments.

#### Scenario: All prompt sources agree
- **WHEN** a Captain check-in is dispatched, combining the persona prompt, the check-in orientation and a resolved order template
- **THEN** every source tells Raven to use `ghostship-spawn` for gateway operations, and none describes an alternative authentication method or a hand-built `curl` call

#### Scenario: Template dispatch step uses the skill
- **WHEN** the `spec-driven-development` or `independent-review` template reaches a dispatch step
- **THEN** it tells Raven to dispatch with `ghostship-spawn <persona>` after writing the pending intent marker, and to record the gateway response's `id` field as the task ID in the confirmation marker

#### Scenario: Claude-backend Raven dispatches without a refusal
- **WHEN** Raven on a claude-backend crew dispatches a persona during a check-in
- **THEN** the dispatch is not refused by the crew's tool gate because of how the call was written

### Requirement: Raven task briefs respect the crew tool gate

Raven SHALL keep `ghostship-spawn` briefs free of literal shell transfer commands and well under 20 KiB. If the skill is unavailable, Raven SHALL report that to the Admiral and hold.

#### Scenario: Helper missing
- **WHEN** a check-in needs a gateway operation and `ghostship-spawn` is not available in the crew
- **THEN** Raven mails the Admiral that the skill is missing and holds, and does not build a `curl` call to the gateway

#### Scenario: Raven briefs avoid literal shell-transfer commands
- **WHEN** Raven prepares a task brief for `ghostship-spawn`
- **THEN** the brief describes file transfers in words, contains no literal upload or download shell pipelines, and remains well under 20 KiB

### Requirement: Raven treats tool refusals as crew gate blocks

A refused gateway tool call SHALL be treated as a crew gate block, not a human decision.

#### Scenario: A refusal is reported, not escalated as an approval request
- **WHEN** a `ghostship-spawn` call is refused by the tool gate
- **THEN** Raven mails the Admiral which operation was refused and holds, without retrying in the same cycle, without offering an "approve" option, and without quoting the command line

#### Scenario: Refused gateway operation reports the affected operation
- **WHEN** the tool gate refuses a gateway operation
- **THEN** Raven reports which operation was refused, holds, does not ask for approval, and does not quote the refused command line in mail

### Requirement: Change artifacts are not Raven's instructions
The built-in `spec-driven-development` and `independent-review` order templates SHALL tell Raven that a change's proposal, specs, design and tasks describe the target behaviour once that change is implemented and the crew relaunched, not Raven's own current instructions. Raven SHALL take its behaviour from its persona prompt, the check-in orientation and the standing orders, even when the change it is driving modifies those.

#### Scenario: A change that edits Raven's own rules
- **WHEN** Raven drives a change whose specs add a rule for Raven (for example "hold if a helper is missing") and that rule is not yet implemented in the crew
- **THEN** Raven does not apply the new rule to itself and continues the lifecycle under its current instructions

#### Scenario: Both templates carry the guidance
- **WHEN** either built-in template is resolved for a check-in
- **THEN** the resolved text states that change artifacts describe target behaviour, not Raven's current instructions

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

### Requirement: Captain standing-orders check-in supports model override

`captain(action="order")` SHALL accept an optional model for new check-in jobs and propagate it to immediate, monitor-fired, and restart-reseeded runs. It SHALL validate the value on every call, including resume; invalid values fail, while a valid value on resume leaves the existing pin unchanged.

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

### Requirement: Captain classifies continuation outcomes

Captain SHALL use structured gateway outcomes for continuation. A status code alone SHALL NOT trigger another write. A busy outcome SHALL preserve the tracked task ID.

#### Scenario: Continuation confirms that the previous session is gone
- **WHEN** the continuation returns a structured rejection confirming a missing session or restore failure
- **THEN** Captain starts recovery by spawning a replacement check-in and tracking its accepted ID

#### Scenario: Continuation returns an unclassified HTTP 400
- **WHEN** the continuation returns HTTP 400 without a supported missing-session or restore-failure reason
- **THEN** Captain surfaces the rejection without another write

#### Scenario: Continuation is busy
- **WHEN** the gateway reports that the current Raven session is busy
- **THEN** Captain retains the tracked task ID

#### Scenario: Continuation acceptance is unknown
- **WHEN** Captain cannot establish whether a continuation or replacement spawn was accepted
- **THEN** Captain adopts an existing task ID only when unique correlation identifies that attempt
- **AND** Captain exposes a hold to the operator without replaying the request when correlation is inconclusive

### Requirement: Captain stop serializes with scheduled check-ins
Captain stop SHALL serialize with per-crew check-in dispatch. When stop returns, no new scheduled check-in dispatch SHALL begin; an already-running check-in may finish before stop returns and SHALL NOT be cancelled.

#### Scenario: Stop waits for an in-flight check-in
- **GIVEN** a scheduled check-in has begun and holds the per-crew transition lock
- **WHEN** `captain(action="stop")` is called
- **THEN** stop waits for that check-in to finish before disabling the schedule and returning

#### Scenario: Check-in starting after stop observes the disabled schedule
- **GIVEN** `captain(action="stop")` has returned successfully
- **WHEN** a scheduled check-in attempts to acquire the per-crew transition lock
- **THEN** it observes the disabled schedule and does not dispatch Raven

### Requirement: Captain order reports success only after consistent persistence
Captain order SHALL report `status: ordered` only after its standing instruction is written and its schedule is persisted enabled. If a persistence step fails, the call SHALL return an error and SHALL NOT leave a schedule enabled without the corresponding instruction.

#### Scenario: Schedule persistence fails before instruction delivery
- **WHEN** Captain cannot persist the schedule transition before writing the standing instruction
- **THEN** the order call returns an error and does not append the instruction to the mailbox

#### Scenario: Instruction delivery fails after a provisional schedule write
- **WHEN** the provisional schedule write succeeds but writing the standing instruction fails
- **THEN** the order call returns an error and leaves the schedule disabled until a later order succeeds

#### Scenario: Final schedule activation fails after instruction delivery
- **WHEN** the standing instruction is written but Captain cannot persist the schedule as enabled
- **THEN** the order call returns an error and the schedule remains disabled

#### Scenario: Schedule and instruction are both persisted
- **WHEN** Captain persists the schedule and writes the standing instruction successfully
- **THEN** the schedule is enabled and the call returns `status: ordered`

# Autonomous Orchestration Specification

## Purpose

Lets the Admiral give a crew's Captain — one per crew, always a recurring check-in loop, never a queue or docket — a standing order, either free-form or the built-in `"sdd"` template driving the standard explore/propose → apply → review → sync/archive persona sequence, so it proceeds without a human dispatching each step.

## Requirements

### Requirement: One Captain check-in per crew

The system SHALL represent a crew's Captain only as one recurring Raven check-in, with no alternate Captain mechanism.

#### Scenario: Admiral stops the Captain
- **WHEN** `captain(crew_id, action="stop")` is called for a crew with a standing-orders check-in loop running
- **THEN** the system pauses the recurring check-in job without deleting it; any persona task already dispatched and running is left to finish on its own, and the mailbox and job history are left as-is for a future `order` to resume from

### Requirement: Captain exposes an explicit action contract

The MCP tool SHALL accept `captain(crew_id, action, message=None, template=None, change_name=None, cron=None, every_secs=None)`, with actions `order`, `stop`, or `status`. `order` SHALL require exactly one of `message` or `template`; `change_name` only substitutes a template value.

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
- **WHEN** `captain(crew_id, action="order", message=<text>, every_secs=<n>)` (or `cron=<expr>`) is called for a crew with no existing check-in job
- **THEN** the system writes `<text>` as mail to `captain@localhost` inside the crew, creates a recurring job dispatching `raven` on the given schedule, and returns the new job's identifier

#### Scenario: Updated standing order for a crew already checking in
- **WHEN** `captain(crew_id, action="order", message=<text>)` is called for a crew with an existing, enabled check-in job
- **THEN** the system writes `<text>` as a new mail message to `captain@localhost`, leaves the existing job's schedule and identifier unchanged, and does not require `every_secs`/`cron` to be repeated

### Requirement: Ordering ensures a recurring Raven check-in

An order SHALL ensure a Raven check-in job exists, creating it only when absent and preserving an existing schedule.

#### Scenario: A schedule is required only when no check-in job exists yet
- **WHEN** `captain(crew_id, action="order", message=<text>)` is called for a crew with no existing check-in job, and neither `every_secs` nor `cron` is given
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
- **THEN** Raven generates a unique local `intent_id`, prefixes the worker task description with `SDD dispatch <change> <persona> <intent_id>`, writes `dispatching <persona> <intent_id>` to `raven@localhost` BEFORE calling `/api/spawn`, and does not invent the gateway's future task ID

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
### Requirement: Standing orders can be composed from a named template
The system SHALL maintain a small, fixed registry of named standing-order templates. When `captain(crew_id, action="order", template=<name>, ...)` is called, the system SHALL resolve `<name>` to that template's text, substituting `change_name` where the template requires it, and SHALL treat the resolved text exactly as a hand-written `message` for every purpose downstream (mailbox write, check-in job creation/reuse). An unknown template name SHALL be rejected before any mail is written.

#### Scenario: Ordering with the built-in SDD template
- **WHEN** `captain(crew_id, action="order", template="sdd", change_name=<name>, every_secs=<n>)` is called
- **THEN** the system resolves the `"sdd"` template, names `<name>` in it, writes the result to `captain@localhost`, and ensures a recurring check-in exists exactly as it would for an equivalent hand-written `message`

#### Scenario: Unknown template name
- **WHEN** `captain(crew_id, action="order", template=<unknown-name>, ...)` is called
- **THEN** the system returns an error naming the unknown template and writes no mail

### Requirement: The built-in SDD template preserves the OpenSpec lifecycle discipline

The `sdd` template SHALL direct Raven through planning, implementation, independent review, and archive, escalate after one unsuccessful fix/re-review cycle, and verify archive state directly.

#### Scenario: Planning incomplete
- **WHEN** a check-in following the `"sdd"` template finds the named change's proposal, design, specs, or tasks artifact not yet done
- **THEN** Raven dispatches Spectre to continue proposing or updating the change, and takes no other dispatching action that check-in

#### Scenario: Unchecked tasks
- **WHEN** a check-in following the `"sdd"` template finds planning complete and at least one unchecked item in `tasks.md`
- **THEN** Raven dispatches Ghost to implement the change's remaining tasks

#### Scenario: Implementation complete, no review yet
- **WHEN** a check-in following the `"sdd"` template finds every `tasks.md` item checked and no review recorded since the last implementation dispatch
- **THEN** Raven dispatches Banshee to independently review the implementation

#### Scenario: Review clean
- **WHEN** Banshee's review reports no unresolved findings
- **THEN** Raven dispatches Reaper to sync specs and archive the change, and confirms archival by reading OpenSpec state on a later check-in rather than assuming it from the dispatch alone

#### Scenario: Review still finds unresolved issues after one fix cycle
- **WHEN** Banshee's review reports unresolved findings, and this is not the first review cycle for the current implementation
- **THEN** Raven escalates to the Admiral rather than dispatching another review or fix cycle
### Requirement: Captain order templates are filesystem-backed
The system SHALL load standing-order templates from individual Markdown files
located in `academy/orders/<name>.md` rather than from the hardcoded
`_ORDER_TEMPLATES` dictionary in `transport/server.py`.

Each template file SHALL contain the raw template body with placeholders.
Template metadata (name, description) SHALL be derived from the filename and
an optional YAML front-matter `description` field.

#### Scenario: Template loaded from academy/orders/
- **WHEN** transport resolves a captain order with `template="sdd"`
- **THEN** the system reads `academy/orders/sdd.md` from the configured academy path and uses its content as the template body

#### Scenario: Template file not found
- **WHEN** transport resolves a captain order with a template name that has no corresponding file in `academy/orders/`
- **THEN** the system raises a ValueError with the message `Unknown Captain order template: '<name>'`

### Requirement: Template placeholder contract
Template files SHALL support the following placeholders, substituted at
resolution time by the transport:

| Placeholder | Resolved to |
|---|---|
| `{{RAVEN_GATEWAY_ORIENTATION}}` | The gateway orientation paragraph (CLI vs REST, credential path) |
| `{{RAVEN_STORE_RESOLUTION}}` | The OpenSpec store registration guidance |
| `{{RAVEN_SELF_CANCEL}}` | The self-cancel instruction for Raven |
| `<change>` | The `change_name` argument passed to `_resolve_order_template` |

#### Scenario: All placeholders resolved
- **WHEN** a template containing all four placeholders is resolved with `change_name="my-change"`
- **THEN** the resolved body contains the full text of each constant and the literal string `my-change` in place of `<change>`

#### Scenario: Missing change_name when template uses <change>
- **WHEN** a template containing `<change>` is resolved with `change_name=None`
- **THEN** the system raises a ValueError indicating that `change_name` is required

### Requirement: transport://orders resource lists templates dynamically
The `transport://orders` MCP resource SHALL enumerate available templates by
scanning the `academy/orders/` directory at call time, returning each
template's name (derived from filename without extension) and description.

#### Scenario: Resource lists all available templates
- **WHEN** a client reads the `transport://orders` resource
- **THEN** the response includes one section per `.md` file found in `academy/orders/`, with the template name and its full body

#### Scenario: No templates on disk
- **WHEN** `academy/orders/` is empty or does not exist
- **THEN** the resource returns `No standing-order templates are available.`

### Requirement: Captain monitor starts a fresh check-in after completion

If `/api/spawn/{task_id}/continue` returns 400 because Raven's prior session is finished, the monitor SHALL clear `current_task_id` and dispatch a fresh check-in.

#### Scenario: Captain monitor recovers after Raven completes
- **WHEN** the captain monitor ticks and the registered `current_task_id` points to a completed Raven task whose gateway session has ended (gateway returns 400 on `/continue`)
- **THEN** the transport falls back to dispatching a fresh Raven check-in via `_dispatch_captain_checkin`, clears `current_task_id` in the registry, and logs an info message — it does NOT log a CrewUnresponsiveError or stall on subsequent ticks

### Requirement: Continue failures do not trigger stale-cookie recovery

A 400 from `/continue` SHALL NOT enter stale-cookie recovery; a 400 from other request paths SHALL retain their existing stale-cookie handling.

#### Scenario: 400 on /continue is not treated as stale cookie
- **WHEN** `/api/spawn/{task_id}/continue` returns `400 Bad Request`
- **THEN** `_crew_api_with_recovery` re-raises the error immediately without entering the stale-cookie retry path

#### Scenario: 400 on other paths still uses stale-cookie recovery
- **WHEN** a non-`/continue` path (e.g. `/api/spawn` dispatch) returns `400 Bad Request`
- **THEN** `_crew_api_with_recovery` continues to route through the existing phase-1 stale-cookie recovery path unchanged
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

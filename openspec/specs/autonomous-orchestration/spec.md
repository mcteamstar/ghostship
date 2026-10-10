# Autonomous Orchestration Specification

## Purpose

Lets the Admiral give a crew's Captain — one per crew, always a recurring check-in loop, never a queue or docket — a standing order, either free-form or the built-in `"sdd"` template driving the standard explore/propose → apply → review → sync/archive persona sequence, so it proceeds without a human dispatching each step.

## Requirements

### Requirement: Exactly one Captain per crew, always a standing-orders check-in
The system SHALL maintain at most one Captain per crew, existing for the lifetime of that crew, always as a scheduled Raven check-in — there SHALL be no other Captain mechanism. The system SHALL expose a `captain(crew_id, action, message=None, template=None, change_name=None, cron=None, every_secs=None)` MCP tool with `action` one of `order`, `stop`, `status`. An `order` call SHALL require exactly one of `message` or `template`; `change_name` is a substitution value used only when the resolved template needs one, never a mode selector.

#### Scenario: Admiral stops the Captain
- **WHEN** `captain(crew_id, action="stop")` is called for a crew with a standing-orders check-in loop running
- **THEN** the system pauses the recurring check-in job without deleting it; any persona task already dispatched and running is left to finish on its own, and the mailbox and job history are left as-is for a future `order` to resume from

#### Scenario: Ordering with both or neither message and template
- **WHEN** `captain(crew_id, action="order", ...)` is called with both `message` and `template` set, or with neither set
- **THEN** the system returns an error and takes no action

### Requirement: Captain status surfaces both mail directions
The system SHALL make `captain(crew_id, action="status")` report unread-message counts for both directions of Captain communication: the existing `unread_mail` field SHALL count the crew's `captain@localhost` standing-order mailbox, and a separate `unread_admiral_mail` field SHALL count the `admiral@localhost` escalation mailbox. The response SHALL identify both mailbox addresses explicitly. This is a pull/fetch-only status surface; it SHALL NOT add a push notification or live-alert mechanism.

#### Scenario: Captain status reports orders and escalations
- **WHEN** `captain(crew_id, action="status")` is called for a crew with unread orders, unread escalations, or both
- **THEN** the response reports the count for `captain@localhost` and the count for `admiral@localhost` separately, including zero when either mailbox is empty or absent

### Requirement: Captain writes standing orders as mail, not a docket entry
For `action="order"`, the system SHALL write `message` as a properly-formatted mail message into the crew's `captain@localhost` mailbox (see `radio-messaging`) from outside the crew container, and SHALL ensure a recurring check-in job exists for that crew dispatching the `raven` persona — creating one if none exists yet, leaving an existing one's schedule untouched if it does. The system SHALL NOT persist the standing orders themselves in any docket file or transport-side state — the mailbox is the sole record, so an `order` call never requires knowing or replaying prior orders.

#### Scenario: First standing order for a crew
- **WHEN** `captain(crew_id, action="order", message=<text>, every_secs=<n>)` (or `cron=<expr>`) is called for a crew with no existing check-in job
- **THEN** the system writes `<text>` as mail to `captain@localhost` inside the crew, creates a recurring job dispatching `raven` on the given schedule, and returns the new job's identifier

#### Scenario: Updated standing order for a crew already checking in
- **WHEN** `captain(crew_id, action="order", message=<text>)` is called for a crew with an existing, enabled check-in job
- **THEN** the system writes `<text>` as a new mail message to `captain@localhost`, leaves the existing job's schedule and identifier unchanged, and does not require `every_secs`/`cron` to be repeated

#### Scenario: A schedule is required only when no check-in job exists yet
- **WHEN** `captain(crew_id, action="order", message=<text>)` is called for a crew with no existing check-in job, and neither `every_secs` nor `cron` is given
- **THEN** the system returns an error and writes no mail, since a brand-new check-in loop has nothing to schedule against

### Requirement: Raven watches the crew and communicates orders on the Captain's recurring loop
The Captain is the recurring check-in loop itself, not any one persona. The system SHALL dispatch the `raven` persona (see `agent-personas`) on each firing of that loop. Each check-in SHALL read the crew's `captain@localhost` mailbox for orders since the prior check-in, assess the crew's current state against those orders as a whole (not only what changed since the previous check-in — this does call for a real, non-mechanical assessment), and take exactly one of: dispatch further work restricted to the five sanctioned personas (`ghost`, `spectre`, `banshee`, `wraith`, `reaper`), steer an already-dispatched persona task still in flight with new context instead of waiting for it to finish, take no action this cycle, or send a message addressed to the Admiral when a decision or permission outside its own authority is required. The system SHALL rely on the check-in job's persistent session for continuity across firings rather than persisting Raven's own state separately. This applies identically regardless of whether the standing order was composed from a template or written free-form.

**Before dispatching any persona**, Raven SHALL apply a layered dispatch-coordination check consisting of three ordered signals:

1. **Mailbox signal (primary):** On each check-in, Raven SHALL scan its own `raven@localhost` mailbox for pending intents (`dispatching <persona> <intent_id>`) and confirmed intents (`dispatching <persona> <spawn_task_id>`). A pending or confirmed intent for the target persona SHALL block another dispatch unless it is stale. Before the spawn call, Raven SHALL generate a unique local intent token in the form `intent-<uuid>` and write the pending subject; because the gateway assigns the real task ID inside `/api/spawn`, Raven SHALL write a confirmation with the returned ID immediately after a successful call rather than inventing that ID beforehand.
2. **Task-description signal (secondary):** Raven SHALL cross-check the `task` field in `kirocrew spawn list` output by content (not the `agent` field) for an in-flight task beginning with the stable marker `SDD dispatch <change> <persona> <intent_id>` and matching the target change and persona.
3. **Agent-field signal (tertiary):** Raven SHALL check the `agent` field on spawn-list entries as a final confirmation only — this field is populated asynchronously and SHALL NOT be relied upon as the sole indicator of whether a persona is already dispatched.

All three layers SHALL report clear before a new pending intent is written. After writing, Raven SHALL re-scan its mailbox; if multiple unconfirmed pending intents target the same persona, only the oldest by Maildir arrival/`Date` (then `Message-ID` for a tie) may proceed, and later markers SHALL hold. If any layer indicates an in-flight or recently dispatched task, Raven SHALL hold that dispatch and re-assess on the next check-in.

To build that assessment, each check-in SHOULD also read the five sanctioned personas' own mailboxes (`/var/mail/ghost`, `/var/mail/spectre`, `/var/mail/banshee`, `/var/mail/wraith`, `/var/mail/reaper`) directly, alongside `kirocrew spawn list`/`cron list`. Reading an mbox file never mutates it (see `radio-messaging`), so this is a plain supplementary read, not a claim on mail addressed to another persona — it surfaces handoffs and blockers personas left for each other that a bare running/done task listing would not show, but it does not substitute for `spawn list` on whether a task has actually finished, since a persona can finish cleanly without writing anything.

There is no native in-session tool for any of this — a dispatched KiroCrew session exposes only ordinary filesystem/shell tools, not an MCP surface for subagent control. Raven SHALL use whichever of two mechanisms actually covers each operation: the `kirocrew` CLI (`spawn list`, `cron list`, `cron pause`, `cron resume`), which authenticates itself internally and requires no credential handling by Raven, for routine task/cron listing and for pausing/resuming its own check-in job; and the crew gateway's own REST API, authenticated by reading the gateway's local IPC credential file and passing it as `X-Internal-Secret` without ever displaying or reporting its value, for named persona dispatch, single-task status detail, steering a running task, and continuing a completed one — none of which the CLI exposes.

#### Scenario: Raven skims persona mailboxes for context
- **WHEN** a check-in assesses the crew's current state
- **THEN** Raven reads each of the five sanctioned personas' own mailboxes directly, in addition to `kirocrew spawn list`/`cron list`, and treats what it finds there as supplementary context rather than a substitute for confirming task completion via `spawn list`

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

#### Scenario: Raven dispatches the next step
- **WHEN** a check-in finds standing orders not yet met and a clear next atomic step within its authority
- **THEN** Raven dispatches one of the five sanctioned personas for that step via an authenticated `POST` to the crew gateway's own `/api/spawn`, without any ghostship transport code parsing or re-issuing that dispatch

#### Scenario: Raven steers an in-flight worker instead of waiting
- **WHEN** new standing orders arrive while a previously-dispatched persona task is still running
- **THEN** Raven sends the new context to that running task via an authenticated `POST` to the gateway's `/api/spawn/{task_id}/steer`, rather than holding until the task finishes and addressing the new orders only on a later cycle

#### Scenario: Raven checks status via the CLI, not a credential
- **WHEN** a check-in needs to know whether previously-spawned work has finished, or the state of its own check-in job
- **THEN** Raven runs `kirocrew spawn list` and `kirocrew cron list` — commands that authenticate themselves — and never reads or passes the gateway's IPC credential for these routine checks

#### Scenario: Raven holds
- **WHEN** a check-in finds no new orders and no outstanding work needing action
- **THEN** Raven takes no dispatching action that cycle, and the job's next firing proceeds on its existing schedule

#### Scenario: Raven escalates instead of guessing
- **WHEN** a check-in encounters a decision or a permission that is outside Raven's own authority to resolve
- **THEN** Raven sends a message to the Admiral's address rather than guessing or unilaterally proceeding, and continues to hold on that point until a reply arrives in a later check-in

#### Scenario: The gateway credential never appears in anything Raven reports
- **WHEN** Raven reads the gateway's local IPC credential file to authenticate a REST call
- **THEN** its actual value never appears in Raven's commentary, reasoning text, task result, or any `pickup`/`bridge`/radio report — it is piped directly from the file into the request header and nowhere else

#### Scenario: Raven cannot be steered by the Admiral
- **WHEN** an Admiral wants to change a standing-orders crew's direction
- **THEN** the only supported channel is a further `captain(action="order", ...)` call — `steer` has no applicable `task_id` for a check-in job, since it is a recurring `schedule` resource, not a `dispatch`-created task; this is unrelated to Raven's own ability to steer the persona tasks it dispatches

### Requirement: Standing orders can be composed from a named template
The system SHALL maintain a small, fixed registry of named standing-order templates. When `captain(crew_id, action="order", template=<name>, ...)` is called, the system SHALL resolve `<name>` to that template's text, substituting `change_name` where the template requires it, and SHALL treat the resolved text exactly as a hand-written `message` for every purpose downstream (mailbox write, check-in job creation/reuse). An unknown template name SHALL be rejected before any mail is written.

#### Scenario: Ordering with the built-in SDD template
- **WHEN** `captain(crew_id, action="order", template="sdd", change_name=<name>, every_secs=<n>)` is called
- **THEN** the system resolves the `"sdd"` template, names `<name>` in it, writes the result to `captain@localhost`, and ensures a recurring check-in exists exactly as it would for an equivalent hand-written `message`

#### Scenario: Unknown template name
- **WHEN** `captain(crew_id, action="order", template=<unknown-name>, ...)` is called
- **THEN** the system returns an error naming the unknown template and writes no mail

### Requirement: The built-in SDD template preserves the OpenSpec lifecycle discipline
The system SHALL ship a `"sdd"` template whose text instructs Raven to: assess the named change's OpenSpec artifact status and `tasks.md` checkbox state as a whole each check-in; dispatch Spectre while planning is incomplete; dispatch Ghost while `tasks.md` has unchecked items once planning is complete; dispatch Banshee for an independent review once implementation is complete; dispatch Reaper to sync specs and archive once a review is clean; and, if a review still finds unresolved issues after one fix-and-re-review cycle, escalate to the Admiral rather than dispatching another review cycle. The template SHALL instruct Raven to confirm the change is archived by reading real OpenSpec state, not by asserting completion from memory alone.

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

### Requirement: Raven persona prompt uses cookie-only auth for spawn calls

The `raven.json` persona prompt SHALL instruct Raven to authenticate all crew
gateway spawn calls using the dashboard session cookie at
`/home/kirocrew/.kiro/crew/.dashboard_cookie`, and SHALL NOT reference
`.local_secret`, `X-Internal-Secret`, or `X-Session-Key` for any spawn-related
instructions. The persona prompt auth instructions SHALL be consistent with the
`_RAVEN_GATEWAY_ORIENTATION` constant in `transport/captain.py`.

The spawn call pattern in the persona prompt SHALL be:

```bash
COOKIE=$(cat /home/kirocrew/.kiro/crew/.dashboard_cookie)
curl -s -X POST http://localhost:5476/api/spawn \
  -H "Cookie: mc_token_5476=$COOKIE" \
  -H "Origin: $(echo $KIROCREW_CORS_ORIGINS | cut -d, -f1)" \
  -H "Content-Type: application/json" \
  -d '{"task": "...", "agent": "<persona>"}'
```

The same cookie-only pattern applies to steer and continue calls. `X-Internal-Secret`
SHALL NOT be sent alongside the cookie on any of these calls.

#### Scenario: Raven on Claude backend reads persona prompt and dispatches

- **WHEN** Raven is dispatched on a Claude backend crew and reads its persona prompt
- **THEN** the persona prompt does not instruct Raven to read `.local_secret` or send
  `X-Internal-Secret`, and Raven's spawn calls use cookie auth without attempting to
  read a credential file directly

#### Scenario: Persona prompt and task text agree on auth method

- **WHEN** Raven receives both its persona prompt (from `raven.json`) and the Captain
  check-in task text (which includes `_RAVEN_GATEWAY_ORIENTATION`)
- **THEN** both sources describe the same cookie-only authentication pattern, with no
  contradiction between them

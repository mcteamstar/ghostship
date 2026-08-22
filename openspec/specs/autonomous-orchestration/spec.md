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

To build that assessment, each check-in SHOULD also read the five sanctioned personas' own mailboxes (`/var/mail/ghost`, `/var/mail/spectre`, `/var/mail/banshee`, `/var/mail/wraith`, `/var/mail/reaper`) directly, alongside `kirocrew spawn list`/`cron list`. Reading an mbox file never mutates it (see `radio-messaging`), so this is a plain supplementary read, not a claim on mail addressed to another persona — it surfaces handoffs and blockers personas left for each other that a bare running/done task listing would not show, but it does not substitute for `spawn list` on whether a task has actually finished, since a persona can finish cleanly without writing anything.

There is no native in-session tool for any of this — a dispatched KiroCrew session exposes only ordinary filesystem/shell tools, not an MCP surface for subagent control. Raven SHALL use whichever of two mechanisms actually covers each operation: the `kirocrew` CLI (`spawn list`, `cron list`, `cron pause`, `cron resume`), which authenticates itself internally and requires no credential handling by Raven, for routine task/cron listing and for pausing/resuming its own check-in job; and the crew gateway's own REST API, authenticated by reading the gateway's local IPC credential file and passing it as `X-Internal-Secret` without ever displaying or reporting its value, for named persona dispatch, single-task status detail, steering a running task, and continuing a completed one — none of which the CLI exposes.

#### Scenario: Raven skims persona mailboxes for context
- **WHEN** a check-in assesses the crew's current state
- **THEN** Raven reads each of the five sanctioned personas' own mailboxes directly, in addition to `kirocrew spawn list`/`cron list`, and treats what it finds there as supplementary context rather than a substitute for confirming task completion via `spawn list`

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

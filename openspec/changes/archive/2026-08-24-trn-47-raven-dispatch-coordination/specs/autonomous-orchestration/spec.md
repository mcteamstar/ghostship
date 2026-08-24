## MODIFIED Requirements

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

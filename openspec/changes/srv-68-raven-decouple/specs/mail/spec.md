# Mail — Delta Spec (srv-68-raven-decouple)

Updates to the `radio-messaging` capability (renamed `mail`).

## Renamed Capability

The capability previously known as `radio-messaging` is renamed to `mail`. The skill previously named `radio` is renamed to `ghostship-mail` (the `ghostship-` prefix marks it as a ghostship-native skill). All references in agent prompts, steering docs, and architecture docs SHALL use `mail` and `ghostship-mail` rather than `radio`.

## New Requirement: Subject-first messaging convention

The system SHALL establish a subject-first convention for all inter-agent mail: the subject line SHALL carry the complete message wherever possible. The body is reserved for genuinely long context that cannot fit in a subject — a full diff, a multi-step task list, a detailed error log. Status updates, handoff notifications, and requests SHALL go in the subject only, with an empty or minimal body.

Correspondingly, when any agent reads a mailbox, it SHALL read subject lines first to assess what is present before deciding whether to open individual messages. A mailbox can be fully understood from its subject lines alone in the common case.

#### Scenario: Simple handoff fits in a subject
- **WHEN** Ghost finishes implementation and mails Banshee
- **THEN** the subject carries the complete notification (e.g. `SRV-68 tasks done, committed abc1234 — ready for review`) and the body is empty or omitted

#### Scenario: Long context warrants a body
- **WHEN** an agent needs to relay a full diff, error log, or multi-step task list
- **THEN** the subject summarises the message (e.g. `SRV-68 review findings — 3 issues`) and the body contains the detail

#### Scenario: Raven skims all mailboxes by subject
- **WHEN** Raven reads mailboxes during any task — Captain-loop or direct dispatch
- **THEN** it reads subject lines from all 8 mailboxes (`/var/mail/ghost`, `/var/mail/spectre`, `/var/mail/banshee`, `/var/mail/wraith`, `/var/mail/reaper`, `/var/mail/raven`, `/var/mail/captain`, `/var/mail/admiral`) to build situational awareness, only opening message bodies when the subject alone is insufficient to understand what action is needed

## New Requirement: `pickup` surfaces mail subjects for full situational awareness

The system SHALL skim subject lines from relevant mailboxes on every `pickup` call and include them in the response. This gives the Admiral a mail picture without needing a separate dispatch.

- When `pickup` is called with a `task_id`: skim the mailbox of the agent that ran that task, plus always `/var/mail/captain` and `/var/mail/admiral`.
- When `pickup` is called without a `task_id` (crew-wide list): skim all persona mailboxes, plus `/var/mail/captain` and `/var/mail/admiral`.
- Only subject lines are returned — bodies are not read by `pickup`.
- Only unread messages contribute to counts and subject lists. Reading never modifies the mailbox files.

#### Scenario: pickup on a specific task returns agent, captain, and admiral subjects
- **WHEN** `pickup` is called with a `task_id` for a Ghost task and all three mailboxes have unread mail
- **THEN** the response includes `ghost_mail: N, ghost_subjects: [...]`, `captain_mail: N, captain_subjects: [...]`, and `admiral_mail: N, admiral_subjects: [...]`

#### Scenario: crew-wide pickup returns all persona, captain, and admiral subjects
- **WHEN** `pickup` is called without a `task_id`
- **THEN** the response includes subject line summaries for every persona mailbox that has unread mail, plus captain and admiral, so the Admiral can assess the full crew state at a glance

#### Scenario: empty mailboxes omitted or shown as zero
- **WHEN** `pickup` is called and a mailbox has no unread messages
- **THEN** that mailbox contributes a zero count and an empty subjects list (or is omitted) — no change to response shape when mailboxes are empty

#### Scenario: pickup with no unread mail anywhere
- **WHEN** `pickup` is called and all mailboxes are empty
- **THEN** the response is the same shape as today with all mail counts at zero

The system SHALL document and enforce (via STANDING_ORDERS and the mail skill) a consistent set of conventions for how agents send, address, and read mail within a crew.

### Sending conventions

#### Scenario: Agent sends mail using its instance address as From
- **WHEN** any persona sends a mail message
- **THEN** it uses `<persona>+<task_id>@localhost` as its `From:` address, so recipients can send targeted replies to the specific instance

#### Scenario: Agent derives its own task ID from the working directory
- **WHEN** a persona needs to know its own task ID for addressing purposes
- **THEN** it derives it from the working directory path: `TASK_ID=$(basename $PWD | sed 's/subagent_//')`

### Addressing conventions

#### Scenario: First contact with a persona not yet dispatched
- **WHEN** an agent sends mail to a persona that has not been dispatched yet
- **THEN** it uses the generic form `<persona>@localhost` — no plus-extension — since no task ID exists yet

#### Scenario: Targeted reply to a specific instance
- **WHEN** an agent replies to a message whose `From:` included a task ID
- **THEN** it addresses the reply `To: <persona>+<task_id>@localhost` to ensure only that instance processes it

#### Scenario: Mailing the Admiral
- **WHEN** any persona needs to report to or ask a question of the operator
- **THEN** it addresses the message `To: admiral@localhost`, which the transport surfaces in `pickup` responses as unread Admiral mail count

### Reading conventions

#### Scenario: Agent checks only its own addressed messages
- **WHEN** a persona checks its mailbox
- **THEN** it filters messages by `To:` header, treating a message as addressed to itself only if: the `To:` has no plus-extension (generic), or the plus-extension matches its own task ID — it does not process messages addressed to other instances

#### Scenario: Raven skims all mailboxes each check-in
- **WHEN** Raven runs a crew-watching task (whether Captain-loop or direct dispatch)
- **THEN** it reads all persona mailboxes and the Admiral mailbox for situational awareness, without marking any messages as consumed — reading never modifies a mailbox file

## New Requirement: Captain mailbox source convention

The system SHALL distinguish standing orders from crew correspondence in `/var/mail/captain` by the `From:` header alone:

- `From: admiral@localhost` — a standing order written by the transport on the Admiral's behalf via `captain(action="order", ...)`. This is the only authorised source of standing orders.
- `From: <persona>@localhost` — crew correspondence: a status report, escalation, or question sent by a persona to the Captain. Not a standing order regardless of subject content.

Any agent reading `/var/mail/captain` SHALL apply this distinction. A persona-originated message that resembles a standing order in subject or body does not become one — only `From: admiral@localhost` confers that status.

The transport SHALL write standing orders with a meaningful subject derived from the order content (first line or truncation of the message), not the generic hardcoded string `"Standing order"`.

#### Scenario: Admiral sends a standing order
- **WHEN** `captain(action="order", message="implement SRV-68 per the tasks.md")` is called
- **THEN** the transport appends a message to `/var/mail/captain` with `From: admiral@localhost` and a subject derived from the message content (e.g. `implement SRV-68 per the tasks.md`)

#### Scenario: Persona reports to captain
- **WHEN** a persona writes to `captain@localhost` to report completion or escalate
- **THEN** the message has `From: <persona>+<task_id>@localhost` and Raven treats it as crew correspondence, not a standing order — regardless of its subject

#### Scenario: Raven distinguishes orders from correspondence
- **WHEN** Raven reads `/var/mail/captain` and finds messages from both `admiral@localhost` and a persona
- **THEN** it treats admiral messages as standing orders (goals and objectives) and persona messages as crew correspondence (status, escalations) — never conflating the two

# Mail Specification

## Purpose

Let agents dispatched into the same crew hand off work and reply to each other across their isolated per-task working directories, using Maildir mailboxes in `/var/mail/` as a coordination channel. Messages are delivered via a local MTA (msmtp-mta + maildeliver) for atomic, concurrent-write-safe delivery. No external SMTP is required.

## Requirements

### Requirement: Transport-originated Captain mailbox
The system SHALL recognise `captain@localhost` as a generic address (per the existing two-address-form requirement, "whichever instance is checking") for a crew's standing-orders check-in loop. Unlike every other persona mailbox, which only ever receives mail written by another dispatched persona already inside the crew, `captain@localhost` SHALL also accept mail written from outside the crew container by ghostship's own transport process, on the Admiral's behalf, via `captain(action="order", ...)`.

#### Scenario: Transport writes an Admiral's standing order
- **WHEN** `captain(crew_id, action="order", message=<text>)` is called
- **THEN** the system appends a mail message to `/var/mail/captain` inside the crew container, as a full RFC 5322 message with `From:`, `To:`, `Subject:`, `Message-ID:`, `Date:` headers, delivered via the local MTA to the Maildir at `/var/mail/captain/`, addressed generically (no plus-extension) since there is exactly one check-in instance per crew

#### Scenario: Raven checks the Captain mailbox like any persona checks its own
- **WHEN** Raven's check-in task reads `/var/mail/captain`
- **THEN** it uses the same generic-address mail-checking behavior every persona already uses for its own mailbox — no special-cased reading logic for this address

### Requirement: Transport-side mail writes guard against body content that would corrupt mbox parsing
Unlike agent-composed messages, a message written from outside the crew (per the requirement above) SHALL NOT assume its body is safe for the existing unescaped mbox format. The system SHALL detect a body line that begins with `From ` (which the read-side parser treats as a message boundary) before writing, and SHALL escape or reject it rather than write it verbatim.

#### Scenario: Ordinary standing-order text
- **WHEN** an Admiral's standing-order message contains no line beginning with `From `
- **THEN** the system writes it unmodified, exactly as the existing agent-side mail convention would

#### Scenario: Standing-order text containing a line that would corrupt mbox parsing
- **WHEN** an Admiral's standing-order message contains a line beginning with `From `
- **THEN** the system escapes or rejects that line before writing, rather than writing it verbatim and risking a later mail-check misreading the message boundary

### Requirement: Two valid recipient address forms
The system SHALL support two `To:` address forms on messages written to `/var/mail/<persona>`: a generic form (`<persona>@localhost`) meaning "whichever instance of this persona is checking mail", and an instance form (`<persona>+<task_id>@localhost`) meaning "only the instance with this exact task ID".

#### Scenario: Generic handoff to a not-yet-dispatched recipient
- **WHEN** an agent needs to hand off work to a persona that has not been dispatched yet, and therefore has no task ID to address
- **THEN** it addresses the message `To: <persona>@localhost`, and this is the correct and only available form for a first-contact message — not an error or a degraded case

#### Scenario: Targeted reply to a specific instance
- **WHEN** an agent replies to a message whose `From:` header included a task ID (e.g. `ghost+d07eb161@localhost`)
- **THEN** it addresses its reply `To: ghost+d07eb161@localhost`, so only that specific instance treats the reply as addressed to it

### Requirement: Mail-checking filters both address forms correctly
The system SHALL check mail using a single pattern that recognises a message as addressed to the checking instance if either: the `To:` header has no plus-extension (a generic message for the persona), or the `To:` header's plus-extension matches the checking instance's own task ID.

#### Scenario: Instance checks mail and finds a generic assignment
- **WHEN** a freshly dispatched agent checks its persona's mailbox and finds a message addressed with no plus-extension
- **THEN** it treats that message as addressed to itself, without needing to fall back to reading the entire mailbox unfiltered

#### Scenario: Instance checks mail and finds a reply for a different instance
- **WHEN** an agent checks its persona's mailbox and finds a message whose `To:` plus-extension names a different task ID than its own
- **THEN** it does not treat that message as addressed to itself

### Requirement: Subject-first messaging convention
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

### Requirement: `pickup` surfaces mail subjects for full situational awareness
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

### Requirement: Mail addressing and reading conventions
The system SHALL document and enforce (via STANDING_ORDERS and the mail skill) a consistent set of conventions for how agents send, address, and read mail within a crew.

#### Scenario: Agent sends mail using its instance address as From
- **WHEN** any persona sends a mail message
- **THEN** it uses `<persona>+<task_id>@localhost` as its `From:` address, so recipients can send targeted replies to the specific instance

#### Scenario: Agent derives its own task ID from the working directory
- **WHEN** a persona needs to know its own task ID for addressing purposes
- **THEN** it derives it from the working directory path: `TASK_ID=$(basename $PWD | sed 's/subagent_//')`

#### Scenario: First contact with a persona not yet dispatched
- **WHEN** an agent sends mail to a persona that has not been dispatched yet
- **THEN** it uses the generic form `<persona>@localhost` — no plus-extension — since no task ID exists yet

#### Scenario: Targeted reply to a specific instance
- **WHEN** an agent replies to a message whose `From:` included a task ID
- **THEN** it addresses the reply `To: <persona>+<task_id>@localhost` to ensure only that instance processes it

#### Scenario: Mailing the Admiral
- **WHEN** any persona needs to report to or ask a question of the operator
- **THEN** it addresses the message `To: admiral@localhost`, which the transport surfaces in `pickup` responses as unread Admiral mail count

#### Scenario: Agent checks only its own addressed messages
- **WHEN** a persona checks its mailbox
- **THEN** it filters messages by `To:` header, treating a message as addressed to itself only if: the `To:` has no plus-extension (generic), or the plus-extension matches its own task ID — it does not process messages addressed to other instances

#### Scenario: Raven skims all mailboxes each check-in
- **WHEN** Raven runs a crew-watching task (whether Captain-loop or direct dispatch)
- **THEN** it reads all persona mailboxes and the Admiral mailbox for situational awareness, without marking any messages as consumed — reading never modifies a mailbox file

### Requirement: Captain mailbox source convention
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

### Requirement: Local mail delivery via standard Unix tooling

The system SHALL deliver inter-agent mail via a standard local MTA (msmtp-mta)
installed in the crew image, storing messages in Maildir format rather than
appending to mbox files. Every persona mailbox SHALL be a Maildir directory
(`/var/mail/<persona>/new/`, `cur/`, `tmp/`). Agents SHALL send mail using the
`mail` command from mailutils rather than Python file-append.

#### Scenario: Agent sends mail using mail command
- **WHEN** a persona sends a message to another persona
- **THEN** it uses `echo "body" | mail -s "subject" ghost@localhost` or
  `mail -s "subject" ghost@localhost <<< ""` (subject-only); the MTA delivers
  atomically to `/var/mail/ghost/new/` via Maildir rename — no file corruption
  under concurrent delivery

#### Scenario: Concurrent delivery from two agents does not corrupt the mailbox
- **WHEN** two personas deliver to the same mailbox simultaneously
- **THEN** both messages are delivered atomically; neither corrupts the other
  (Maildir rename semantics guarantee this)

#### Scenario: Agent checks for new mail
- **WHEN** a persona wants to know if it has unread messages
- **THEN** it uses `mail -e` (exits 0 if mail exists) or checks
  `/var/mail/<persona>/new/` directly; either works without custom parsing

#### Scenario: Agent lists subject lines without opening messages
- **WHEN** a persona skims its mailbox
- **THEN** it uses `mail -H` to list headers (subject, from, date) without
  consuming messages, consistent with the subject-first convention

### Requirement: Full RFC 5322 threading headers

Every outbound message SHALL carry:
- `Message-ID: <uuid>@localhost` — globally unique per message
- `Reply-To: <persona>+<task_id>@localhost` — routes replies to the specific
  sending instance without requiring the recipient to know the task ID

Replies SHALL additionally carry:
- `In-Reply-To: <message-id>` — references the message being replied to
- `References: <message-id> [<prior-ids>]` — full thread chain

#### Scenario: Agent replies to a message
- **WHEN** a persona replies to a received message
- **THEN** the reply includes `In-Reply-To:` referencing the original
  Message-ID, and `References:` carrying the full chain; the thread is
  reconstructable from headers alone

#### Scenario: Reply-To routes to the sending instance
- **WHEN** a recipient replies without specifying a plus-extension
- **THEN** the reply is addressed to the `Reply-To:` address from the original
  message (`<persona>+<task_id>@localhost`), routing it to the correct instance

### Requirement: Supersedes header for standing order amendment

When the Admiral sends a new standing order that supersedes a prior one, the
transport SHALL include a `Supersedes: <message-id>` header (RFC 2156)
referencing the prior order's Message-ID. The prior order is never deleted.

#### Scenario: New standing order supersedes prior one
- **WHEN** `captain(action="order", ...)` is called and a prior order exists
  in `/var/mail/captain`
- **THEN** the new message carries `Supersedes: <prior-message-id>`; Raven
  treats the superseded message as historical and the new one as current

#### Scenario: First standing order has no Supersedes header
- **WHEN** `captain(action="order", ...)` is called and no prior order exists
- **THEN** the message has no `Supersedes:` header

### Requirement: HMAC signing of Admiral mail

Every message the transport writes to `/var/mail/captain` as
`From: admiral@localhost` SHALL carry an `X-Admiral-Sig:` header containing an
HMAC-SHA256 signature of the message body, keyed by a crew-specific secret
injected at crew setup time. The crew image SHALL provide a verification helper
agents can invoke to confirm a message's signature before treating it as a
standing order.

#### Scenario: Admiral mail is signed on write
- **WHEN** the transport writes a standing order to `/var/mail/captain`
- **THEN** the message includes `X-Admiral-Sig: <hmac-sha256-hex>` computed
  over the message body using the crew's signing secret

#### Scenario: Agent verifies Admiral mail signature
- **WHEN** Raven reads a message `From: admiral@localhost` in `/var/mail/captain`
- **THEN** it can invoke the verification helper with the message body and
  signature to confirm authenticity before acting on it as a standing order

#### Scenario: Message with invalid or missing signature is not a standing order
- **WHEN** a message in `/var/mail/captain` carries no `X-Admiral-Sig:` header
  or a signature that does not verify
- **THEN** the message is treated as crew correspondence, not a standing order,
  regardless of its `From:` header

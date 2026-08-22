## Purpose

Let agents dispatched into the same crew hand off work and reply to each other across their isolated per-task working directories, using mbox files in `/var/mail/` as a coordination channel with no MTA required.

## Requirements

### Requirement: Transport-originated Captain mailbox
The system SHALL recognise `captain@localhost` as a generic address (per the existing two-address-form requirement, "whichever instance is checking") for a crew's standing-orders check-in loop. Unlike every other persona mailbox, which only ever receives mail written by another dispatched persona already inside the crew, `captain@localhost` SHALL also accept mail written from outside the crew container by ghostship's own transport process, on the Admiral's behalf, via `captain(action="order", ...)`.

#### Scenario: Transport writes an Admiral's standing order
- **WHEN** `captain(crew_id, action="order", message=<text>)` is called
- **THEN** the system appends a mail message to `/var/mail/captain` inside the crew container, in the same mbox format (envelope line, `From:`/`To:`/`Subject:`/`Date:` headers, blank line, body) every existing persona-to-persona message already uses, addressed generically (no plus-extension) since there is exactly one check-in instance per crew

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

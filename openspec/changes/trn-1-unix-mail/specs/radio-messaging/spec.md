# Mail — Delta Spec (srv-69-unix-mail)

Updates to the `radio-messaging` capability.

## Modified Requirement: Local mail delivery via standard Unix tooling

Replace the existing delivery requirement with:

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

## New Requirement: Full RFC 5322 threading headers

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

## New Requirement: Supersedes header for standing order amendment

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

## New Requirement: HMAC signing of Admiral mail

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

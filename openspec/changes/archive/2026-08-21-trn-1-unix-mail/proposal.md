## Why

The current inter-agent mail system hand-appends RFC 2822-formatted text directly
to mbox files in `/var/mail/` via a Python one-liner. It works, but it has real
problems: mbox appends are not atomic (concurrent writes from two agents can
corrupt the file), there is no Message-ID so replies cannot thread, the `From `
line delimiter requires body escaping, and the `mail` command cannot be used
because no MTA is installed. The result is a simulation of a mailbox rather than
a real one.

The right substrate — as argued in "The Mailbox Is the Memory" (Bailey & Cora 7,
2026) — is RFC 5322 messages in Maildir, delivered by a real local MTA, indexed
and read with standard mail tooling. This change replaces the hand-rolled stack
with a proper local mail system, keeping everything inside the container (no
external SMTP, no outside delivery) and giving agents the full Unix mail UX.

## What Changes

**Delivery substrate:**
- Switch from mbox file-append to **Maildir** — one file per message, atomic
  delivery via rename, no corruption under concurrent writes, natively supported
  by notmuch (available as a zero-migration upgrade later).
- Install **msmtp-mta** as the sendmail-compatible MTA interface (local delivery
  only, no external SMTP relay, no open ports) and **procmail** for delivery
  routing including plus-address extension handling
  (`ghost+<task_id>@localhost` → `/var/mail/ghost/`).
- Install **mailutils** so agents send with `mail -s "subject" ghost@localhost`
  and check with `mail -e` / `mail -H` (header list) instead of Python heredocs.

**Full RFC 5322 threading:**
- Every outbound message gets a `Message-ID: <uuid>@localhost` header.
- Replies include `In-Reply-To:` and `References:` headers — threads are
  provenance for free, no extra work required.
- Every outbound message sets `Reply-To: <persona>+<task_id>@localhost` so
  recipients can reply to the specific instance without knowing its task ID in
  advance.

**Supersedes header for standing order amendment:**
- When Admiral sends a new standing order that supersedes a prior one, the
  transport writes a `Supersedes: <message-id>` header (RFC 2156) referencing
  the old order's Message-ID. Raven can identify which orders are current without
  re-reading the full history.
- Old orders are never deleted — the mbox/Maildir record is append-only.

**Cryptographic signing of Admiral mail (transport-side):**
- The transport (ga-transport) holds an HMAC secret injected at crew setup time
  (written to a crew-specific file in the workspace, not the agent's environment).
- Every message written to `/var/mail/captain` as `admiral@localhost` is HMAC-
  signed; the signature is carried in an `X-Admiral-Sig:` header.
- The crew image ships a verification helper agents can call to confirm a message
  is genuine before acting on it as a standing order. A message without a valid
  signature is crew correspondence, not an Admiral order, regardless of the
  `From:` header.

**Transport and skill updates:**
- `_write_captain_mail` in `transport/server.py` — replace Python file-append
  with MTA delivery, add Message-ID generation, add Supersedes header support,
  add HMAC signing.
- `academy/skills/ghostship-mail/SKILL.md` — replace Python heredoc send
  examples with `mail` command examples; update read examples to use `mail -H`
  for subject listing; document threading headers and Reply-To convention.
- `academy/steering/STANDING_ORDERS.md` — update send/receive conventions to
  use `mail` command; document Supersedes and threading.
- `crews/kirocrew/Containerfile` — add msmtp-mta, procmail, mailutils packages;
  add Maildir provisioning script; configure procmail for plus-addressing.

## Capabilities

### New Capabilities
_(none)_

### Modified Capabilities
- `mail`: delivery mechanism changes from Python-appended mbox to Maildir via
  local MTA; threading headers added; Supersedes header for standing orders;
  HMAC signing of Admiral mail; `mail` command replaces Python heredoc in skill.

## Impact

- `crews/kirocrew/Containerfile` — package installs, Maildir provisioning,
  procmail configuration
- `transport/server.py` — `_write_captain_mail` rewrite, Message-ID generation,
  Supersedes support, HMAC signing, HMAC secret injection at crew setup
- `academy/skills/ghostship-mail/SKILL.md` — updated send/receive examples
- `academy/steering/STANDING_ORDERS.md` — updated mail conventions
- No MCP tool interface changes; no breaking changes to pickup or captain tools
- Agents using the Python heredoc pattern will need to migrate to `mail` command
  (documented in the skill); the mbox files at `/var/mail/` become Maildir
  directories — existing crews will need to be nuked and relaunched

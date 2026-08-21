# Design — srv-69-unix-mail

## Context

See proposal.md — Why.

Current state in `crews/kirocrew/Containerfile`:
```
# Radio skill: agent mailboxes as plain mbox files — no MTA needed.
RUN mkdir -p /var/mail && chmod 1777 /var/mail
```

Agents write RFC 2822 messages via a Python heredoc one-liner. The transport
writes to `/var/mail/captain` the same way. No MTA, no threading headers, no
atomic delivery guarantees.

## Goals

- `mail -s "subject" ghost@localhost` works inside the crew container
- Delivery is atomic (Maildir rename, not mbox append)
- Full threading headers on every message (Message-ID, Reply-To; In-Reply-To +
  References on replies)
- Supersedes header when transport writes a replacement standing order
- HMAC-signed Admiral mail; crew image ships a verification helper
- ghostship-mail skill examples updated to use `mail` command
- No external SMTP — local delivery only, no open ports, no relay config

## Non-Goals

- notmuch indexing (designed for v2 — Maildir is already compatible)
- Per-persona Unix system users (personas share the `kirocrew` user; Maildir
  directories provide the isolation needed)
- External SMTP or cross-host delivery
- Encryption of agent mail (deliberately not done — audit surface must stay
  readable by the principal)

## Approach

### 1. Containerfile — package installation and Maildir provisioning

```dockerfile
# ghostship-mail: proper local mail delivery via mailutils + msmtp-mta + procmail
# Replaces hand-rolled mbox file-append. Local delivery only — no external SMTP.
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
      mailutils msmtp msmtp-mta procmail && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Provision Maildir mailboxes for all 7 addresses
# (6 personas + captain; admiral is transport-side only)
RUN for mb in ghost spectre banshee wraith reaper raven captain; do \
      install -d -m 700 /var/mail/$mb/new /var/mail/$mb/cur /var/mail/$mb/tmp; \
    done && chmod 1777 /var/mail
```

### 2. procmail configuration — plus-address routing

`/etc/procmailrc` (global, applies to all local delivery):
```
MAILDIR=/var/mail
DEFAULT=$MAILDIR/$LOGNAME/

# Route plus-addressed mail to the base persona's Maildir
# e.g. ghost+abc123@localhost → /var/mail/ghost/
:0
* ^TO_.*\+[^@]*@localhost
| formail -I "X-Original-To: $MATCH" >> $MAILDIR/$(echo "$MATCH" | sed 's/\+.*//')/
```

Actually simpler: use `.procmailrc` per-user or configure msmtp-mta to route
locally. Since all personas share the `kirocrew` user, procmail must route by
`To:` header not by Unix user. A simple wrapper script is cleaner:

`/usr/local/bin/maildeliver`:
```bash
#!/bin/bash
# Deliver stdin to the Maildir for the given address, stripping plus-extension
addr="${1%%@*}"       # strip @localhost
base="${addr%%+*}"    # strip +task_id
exec maildrop -d kirocrew /var/mail/$base/
```

Configure msmtp-mta to use this for local delivery in `/etc/msmtprc`.

### 3. msmtp-mta configuration

`/etc/msmtprc`:
```
defaults
  logfile /var/log/msmtp.log

account local
  host localhost
  port 25
  from kirocrew@localhost
  delivery maildir /var/mail/
```

Actually: since msmtp is primarily an SMTP client, for local-only delivery the
cleanest approach is to configure it to pipe through `maildrop` or use
`sendmail` compat wrapper. Standard approach on Debian:

```
# /etc/msmtprc
defaults
  auto_from on
  maildrop /usr/bin/maildrop

account default
  host 127.0.0.1   # local only — no external relay
```

An alternative that avoids the msmtp complexity: use **msmtp** just for the
`sendmail` interface, and configure it to pipe to a local delivery script.
The `mailutils` package's `mail` command uses `/usr/sbin/sendmail` by default.

Simplest working config for local-only delivery:
- Install `msmtp-mta` (provides `/usr/sbin/sendmail` compat)
- Configure `/etc/msmtprc` to deliver locally via maildrop
- Test: `echo "test" | mail -s "test" ghost@localhost`

### 4. Message-ID and threading in ghostship-mail skill

The skill's send helper needs updating to generate and include threading headers.
New send pattern:

```bash
send_mail() {
  local to="$1" subject="$2" body="${3:-}"
  local task_id=$(basename $PWD | sed 's/subagent_//')
  local persona=$(whoami)  # or derive from agent name
  local msg_id="<$(uuidgen)@localhost>"
  local ts=$(date -R)

  {
    echo "From: ${persona}+${task_id}@localhost"
    echo "To: ${to}"
    echo "Subject: ${subject}"
    echo "Message-ID: ${msg_id}"
    echo "Reply-To: ${persona}+${task_id}@localhost"
    echo "Date: ${ts}"
    echo ""
    [ -n "$body" ] && echo "$body"
  } | /usr/sbin/sendmail "$to"
}
```

Reply helper (includes In-Reply-To + References):
```bash
reply_mail() {
  local to="$1" subject="$2" in_reply_to="$3" references="$4" body="${5:-}"
  local task_id=$(basename $PWD | sed 's/subagent_//')
  local persona=$(whoami)
  local msg_id="<$(uuidgen)@localhost>"
  local ts=$(date -R)

  {
    echo "From: ${persona}+${task_id}@localhost"
    echo "To: ${to}"
    echo "Subject: ${subject}"
    echo "Message-ID: ${msg_id}"
    echo "Reply-To: ${persona}+${task_id}@localhost"
    echo "In-Reply-To: ${in_reply_to}"
    echo "References: ${references} ${in_reply_to}"
    echo "Date: ${ts}"
    echo ""
    [ -n "$body" ] && echo "$body"
  } | /usr/sbin/sendmail "$to"
}
```

### 5. Transport: `_write_captain_mail` rewrite

Current: Python string-append to `/var/mail/captain` as a flat mbox file.
New: pipe through MTA inside the container via `container_exec`.

Key changes:
- Generate `Message-ID` (uuid) for each message
- Store last Message-ID in registry so next order can reference it with `Supersedes:`
- Compute HMAC-SHA256 of body using crew signing secret; include as `X-Admiral-Sig:`
- Use `podman exec` to pipe the formatted message through `sendmail captain@localhost`
  rather than appending to `/var/mail/captain` directly

HMAC signing secret: injected at `_finish_crew_setup` time — generate a random
32-byte hex secret, write to `/home/kirocrew/workplace/.admiral_secret` (not in
agent PATH, not in env), update registry with the secret for re-use on future orders.

### 6. Verification helper in crew image

`/usr/local/bin/verify-admiral-sig`:
```python
#!/usr/bin/env python3
"""Verify X-Admiral-Sig on a message read from stdin."""
import sys, hmac, hashlib, email

secret_path = '/home/kirocrew/workplace/.admiral_secret'
msg = email.message_from_file(sys.stdin)
sig = msg.get('X-Admiral-Sig', '')
body = msg.get_payload()

try:
    secret = open(secret_path).read().strip().encode()
except FileNotFoundError:
    sys.exit(2)  # secret not available

expected = hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()
if hmac.compare_digest(sig, expected):
    sys.exit(0)  # valid
else:
    sys.exit(1)  # invalid
```

### 7. Migration note

Existing crews use mbox files at `/var/mail/<persona>`. After this change the
same paths become Maildir directories. Existing crews must be nuked and
relaunched — the Containerfile change is a breaking image update. Document this
in the commit message and in a migration note in docs/architecture.md.

## Files Changed

- `crews/kirocrew/Containerfile` — package installs, Maildir provisioning
- `crews/kirocrew/verify-admiral-sig` — new HMAC verification helper (COPY into image)
- `transport/server.py` — `_write_captain_mail` rewrite, Message-ID tracking in
  registry, HMAC signing, Supersedes header, HMAC secret injection at setup
- `academy/skills/ghostship-mail/SKILL.md` — updated send/reply examples with
  threading headers
- `academy/steering/STANDING_ORDERS.md` — updated mail conventions
- `docs/architecture.md` — migration note, updated mail description

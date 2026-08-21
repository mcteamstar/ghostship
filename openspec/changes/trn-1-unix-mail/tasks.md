# Tasks — srv-69-unix-mail

## Task 1 — Update Containerfile: install mail packages and provision Maildir

File: `crews/kirocrew/Containerfile`

Replace the current radio comment and `mkdir /var/mail` with:

```dockerfile
# ghostship-mail: proper local mail delivery via mailutils + msmtp-mta + procmail
# Replaces hand-rolled mbox file-append. Local delivery only — no external SMTP.
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
      mailutils msmtp msmtp-mta procmail && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Provision Maildir mailboxes for all 7 local addresses
# (6 personas + captain; admiral is written by the transport only)
RUN for mb in ghost spectre banshee wraith reaper raven captain; do \
      install -d -m 700 /var/mail/$mb/new /var/mail/$mb/cur /var/mail/$mb/tmp; \
    done && chmod 1777 /var/mail
```

## Task 2 — Configure local mail delivery

File: `crews/kirocrew/` (new config files copied into image)

Create `crews/kirocrew/msmtprc` for local-only delivery config and
`crews/kirocrew/procmailrc` (or a delivery wrapper script) for plus-address
routing (`ghost+abc123@localhost` → `/var/mail/ghost/`).

Update `Containerfile` to COPY these into the image at the right paths
(`/etc/msmtprc`, `/etc/procmailrc` or `/usr/local/bin/maildeliver`).

Test inside a built container: `echo "" | mail -s "test subject" ghost@localhost`
should deliver atomically to `/var/mail/ghost/new/`.

## Task 3 — Add HMAC verification helper to crew image

File: `crews/kirocrew/verify-admiral-sig` (new, copied into image)

Write the Python verification helper (see design.md §6). COPY it into the image
at `/usr/local/bin/verify-admiral-sig` with execute permission. The helper:
- Reads a raw RFC 5322 message from stdin
- Reads the signing secret from `/home/kirocrew/workplace/.admiral_secret`
- Exits 0 if `X-Admiral-Sig:` matches, 1 if mismatch, 2 if secret not found

## Task 4 — Rewrite `_write_captain_mail` in transport

File: `transport/server.py`

Replace the Python file-append implementation with MTA delivery:
- Generate `Message-ID: <uuid>@localhost` for each message
- Read previous Message-ID from registry (if any) to include `Supersedes:` header
- Compute `X-Admiral-Sig: <hmac-sha256-hex>` over the message body using the
  crew's signing secret (read from registry, see Task 5)
- Pipe the fully-formed RFC 5322 message through
  `container_exec(container, ["sendmail", "captain@localhost"])` rather than
  appending to `/var/mail/captain` directly
- Store the new Message-ID in the registry for the next call's Supersedes header

Update `_format_captain_mail` signature and implementation accordingly.

## Task 5 — Inject HMAC signing secret at crew setup

File: `transport/server.py`

In `_finish_crew_setup`, after the gateway is ready:
- Generate a random 32-byte hex secret: `secrets.token_hex(32)`
- Write it to `/home/kirocrew/workplace/.admiral_secret` inside the container
  via `container_exec` (mode 0600, owned by kirocrew)
- Store it in the registry under the crew entry so `_write_captain_mail` can
  read it on subsequent calls without re-reading the container file each time

## Task 6 — Update ghostship-mail skill with new send/reply patterns

File: `academy/skills/ghostship-mail/SKILL.md`

Replace the Python heredoc send examples with `mail` command examples that
include threading headers. Add:
- Send helper function using `sendmail` directly (for full header control)
- Reply helper function that adds `In-Reply-To:` and `References:`
- `mail -H` for subject-line listing
- `mail -e` for checking unread mail
- Note on reading Message-ID from received messages for reply threading

## Task 7 — Update STANDING_ORDERS.md mail conventions

File: `academy/steering/STANDING_ORDERS.md`

Update the mail conventions section to:
- Use `mail` command examples instead of Python heredoc
- Add Message-ID and Reply-To as required headers on every outbound message
- Add In-Reply-To / References for replies
- Note the Supersedes convention for standing order amendments
- Note `verify-admiral-sig` for confirming Admiral mail authenticity

## Task 8 — Add migration note to docs/architecture.md

File: `docs/architecture.md`

Add a note under the mail/workarounds section:
- Existing crews (pre-srv-69) use mbox files at `/var/mail/<persona>`
- After this change the image uses Maildir directories at the same paths
- Existing crews must be nuked and relaunched — the image change is not
  backward-compatible with existing mbox mailboxes

## Task 9 — Build and smoke-test the new crew image

```bash
# Build the new image
cd crews/kirocrew && podman build -t localhost/kirocrew-crew:latest .

# Launch a test crew
# (via MCP: launch(crew_id="test-mail"))

# Test local delivery
podman exec gs-test-mail bash -c '
  echo "" | mail -s "test subject" ghost@localhost &&
  ls /var/mail/ghost/new/ &&
  mail -H -f /var/mail/ghost/
'

# Test plus-addressing
podman exec gs-test-mail bash -c '
  echo "" | mail -s "instance test" ghost+abc123@localhost &&
  ls /var/mail/ghost/new/
'

# Test concurrent delivery (two processes simultaneously)
# Both messages should arrive without corruption

# Verify Maildir structure
podman exec gs-test-mail ls -la /var/mail/ghost/
```

All tests pass before committing. Nuke the test crew after verification.

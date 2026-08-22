## Why

Radio (`radio-messaging`) works today by having agents hand-append RFC 2822-formatted
text directly to `/var/mail/<persona>` via a Python one-liner — no MTA, no real
mail delivery, just a flat file and a bit of header-parsing on read. It works, but
it's a hand-rolled simulation of a mailbox rather than an actual one.

This is a stub only — capturing a direction Tony wants kept alive for a future
planning pass, not a worked-out design. No implementation should start from this
proposal as written.

## What Changes (sketch, not final)

- Give each of the five personas (Ghost, Spectre, Banshee, Wraith, Reaper) a real
  Unix system user inside the crew container, instead of them all running as one
  shared OS user with persona identity existing only at the kiro-cli/agent layer.
- Install a proper local mail client/MTA (e.g. `mailutils`/`bsd-mailx` plus a local
  delivery path — `sendmail`/`postfix`, or something lighter) in
  `crews/kirocrew/Containerfile`, so sending mail is `mail -s "subject" <persona>`
  instead of a Python heredoc, and delivery lands in the standard `/var/mail/<user>`
  spool via the OS's own local-delivery path rather than a script appending to it.
- **Cryptographic signing of Admiral mail** — the transport (ga-transport) holds a
  private key and signs every message it writes to `/var/mail/captain` as
  `admiral@localhost`. The crew image ships the corresponding public key so any
  persona can verify the signature without being able to forge one. Agents reading
  `/var/mail/captain` can confirm `From: admiral@localhost` is genuine and not
  spoofed by another agent writing directly to the mbox file. Candidate approaches:
  GPG/PGP inline signatures (well-understood, `gpg` available on most base images),
  or a simpler HMAC scheme using a shared secret injected at crew setup time (less
  infrastructure, same threat model for an isolated container). The threat model is
  intra-container spoofing — one persona writing to another's mailbox to fake Admiral
  authority — not external adversaries.
- Open questions for the real design pass: how the existing
  `<persona>+<task_id>@localhost` instance-addressing convention (see
  `radio-messaging`'s two-address-form requirement) maps onto a real MTA — plus-
  addressing usually needs explicit alias/procmail-style routing rules, which is
  real config weight a flat file never needed; whether per-persona system users
  need real login shells/permissions or can be mail-only; how this interacts with
  the crew image build (`crews/kirocrew/Containerfile`) and `seed_kiro_db.py`;
  whether the read side (`skills/radio/SKILL.md`'s filtering logic) still needs
  custom parsing regardless, since a real client's read UX doesn't natively
  understand the generic-vs-instance addressing split; whether this is worth the
  added daemon/config surface over the current zero-dependency file-append, given
  personas are ephemeral per-crew and not long-lived accounts anyone logs into
  directly.

## Capabilities

### Modified Capabilities
- `radio-messaging`: the delivery mechanism changes from a Python-appended mbox
  file to real local mail delivery — not yet specced, pending the real design pass.

## Impact

- `academy/skills/radio/SKILL.md`, `crews/kirocrew/Containerfile`,
  `crews/kirocrew/seed_kiro_db.py`, `academy/steering/STANDING_ORDERS.md`.
- Not yet scoped: exact MTA/mail client choice, per-persona user provisioning,
  how plus-addressing survives the move, whether the read-side filtering logic
  in the radio skill can simplify or stays as-is.

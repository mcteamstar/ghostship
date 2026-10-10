## Why

The `maildeliver` script builds its target Maildir path by interpolating the recipient address directly into a filesystem path (`MAILDIR="/var/mail/${BASE}"`), where `BASE` is the local-part of the recipient with only the `@domain` and `+extension` stripped. Nothing validates that `BASE` names one of the known crew personas. A recipient such as `../../etc/cron.d/evil@localhost` or `/root/.ssh/authorized_keys@localhost` makes `maildeliver` call `mkdir -p` and write an attacker-controlled file **outside** `/var/mail/`, because the local MTA invokes `maildeliver` with whatever recipient appears on an inbound message. Since inter-agent mail is the crew's trusted coordination channel and any dispatched agent (or injected content that reaches a `maildeliver`/`mail` call) can set the recipient, this is a path-traversal / arbitrary-file-write vulnerability that must be closed at the delivery boundary.

## What Changes

- Harden `maildeliver` to reject any recipient whose derived mailbox name is not a valid, known persona mailbox before any filesystem operation:
  - Validate the derived base name against a strict allowlist / character class — the base MUST match `^[a-z][a-z0-9_-]*$` (lowercase, no path separators, no `.`/`..`, no leading dot, no slashes).
  - Reject any recipient containing a path separator (`/`), a parent-directory segment (`..`), a leading `.`, a NUL byte, or an empty base, with a non-zero exit and a diagnostic on stderr — **before** `mkdir -p` or any write.
  - Pin delivery to `/var/mail/` by resolving the final path and confirming it is a direct child of `/var/mail/` (defense in depth, so no interpolation can escape even if the base check is bypassed).
- Preserve all existing legitimate behavior: `@domain` stripping, `+extension` plus-address stripping, Maildir `tmp/` → `new/` atomic rename, and the generic/instance address forms.
- No change to how agents send mail; valid persona recipients (`ghost`, `spectre`, `banshee`, `wraith`, `reaper`, `raven`, `captain`, `admiral`, and their `+task_id` instance forms) continue to deliver exactly as today.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `mail`: The "Local mail delivery via standard Unix tooling" / `maildeliver` delivery behavior gains a requirement that recipient-derived mailbox paths MUST be validated and confined to `/var/mail/`, rejecting path-traversal and absolute-path recipients. This is a spec-level behavioral change: a previously-accepted (malicious) recipient is now rejected, and delivery is guaranteed to stay within `/var/mail/`.

## Impact

- **Code**: `crews/_base/admission/maildeliver` (the delivery script baked into the crew image). The hardening is a localized change at the top of the script, before any `mkdir`/`cat`/`mv`.
- **Behavior**: Malformed or traversal recipients now cause a non-zero exit with a stderr diagnostic instead of writing outside `/var/mail/`. Legitimate persona deliveries are unaffected.
- **Security**: Closes an arbitrary-file-write / path-traversal vector in the crew's trusted mail channel (TRN-217). No external surface; the fix is defense-in-depth at the local delivery boundary.
- **Dependencies / APIs**: None added. Pure bash validation using existing shell builtins.
- **Spec**: `openspec/specs/mail/spec.md` gains a delta requirement; the `ghostship-mail` skill and `STANDING_ORDERS.md` need no change (they already only ever use valid persona recipients).

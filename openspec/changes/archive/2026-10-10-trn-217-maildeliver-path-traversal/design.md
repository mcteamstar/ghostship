## Context

See `proposal.md — Why` for motivation.

`maildeliver` (bash, ~30 lines) is called by msmtp-mta for every local mail delivery. The vulnerability is at lines:

```
LOCAL="${RECIPIENT%%@*}"
BASE="${LOCAL%%+*}"
MAILDIR="/var/mail/${BASE}"
mkdir -p "${MAILDIR}/new" ...
```

No validation occurs between receiving `RECIPIENT` on the command line and using `BASE` in a filesystem path. `sendmail-local` delegates straight to `maildeliver` with no prior checks.

## Goals / Non-Goals

**Goals:**
- Reject any recipient whose BASE does not match `^[a-z][a-z0-9_-]*$` before touching the filesystem
- Apply the same guard in `sendmail-local` as defense-in-depth
- Cover the fix with a shell test

**Non-Goals:**
- Validating the `@domain` portion (only `localhost` is used, but that's enforced by routing, not this script)
- Allowlisting specific persona names (the regex is sufficient; exact persona names can grow without code changes)
- Hardening against other classes of input (excessively long inputs are implicitly rejected by the regex failing to match)

## Decisions

**Regex over allowlist** — `^[a-z][a-z0-9_-]*$` permits any lowercase identifier without enumerating persona names. An allowlist would require updating `maildeliver` whenever a new persona is added; the regex never needs to change. Alternative: hardcode the eight known persona names. Rejected — brittle against persona expansion and provides no real additional security benefit.

**Validate in both scripts** — `sendmail-local` could rely entirely on `maildeliver`'s guard. Adding the check in `sendmail-local` too fails fast before spawning a subprocess and makes both scripts independently auditable. Cost is two extra lines; benefit is clear defence-in-depth.

**Exit 1 on bad input, no silent drop** — Silently ignoring a bad recipient could mask misconfiguration. Printing to stderr and exiting 1 surfaces the error to callers (and msmtp-mta logs it).

**Validation placement in `maildeliver`** — The check goes immediately after `BASE` is derived, before the `MAILDIR` assignment. This ensures no filesystem path is ever constructed from an unvalidated value.

## Risks / Trade-offs

- **Regex too permissive** → The pattern `^[a-z][a-z0-9_-]*$` still allows arbitrary identifiers like `zzz` — but that only lets an actor write into `/var/mail/zzz`, not escape the mail root. Full escape requires `.` or `/`, both blocked.
- **Breaks callers passing non-lowercase addresses** → No current caller does this; all personas use lowercase names. The fix aligns with documented addressing conventions.

## Migration Plan

Drop-in replacement of two shell scripts. No Maildir state changes. No container rebuild required beyond including the updated files in the next image layer.

Rollback: revert the two script files; no data migration needed.

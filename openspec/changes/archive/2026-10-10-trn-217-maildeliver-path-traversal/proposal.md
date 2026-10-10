## Why

`maildeliver` derives the Maildir path directly from the recipient argument (`/var/mail/${BASE}`) without validating `BASE` against an allowlist of known persona names. An attacker — or a buggy agent — who supplies `../../tmp/x@localhost` as a recipient causes delivery to `/var/mail/../../tmp/x`, writing arbitrary files outside the mail root. The fix is a one-line regex guard before any filesystem access.

## What Changes

- **maildeliver**: validate `BASE` matches `^[a-z][a-z0-9_-]*$` before the `mkdir`/write path; reject with exit 1 on failure.
- **sendmail-local**: same validation applied before delegating to `maildeliver`, providing defense-in-depth.
- **Tests**: add a shell test (`tests/unit/test_maildeliver.sh`) covering acceptance of valid recipients and rejection of path traversal and other malformed inputs.

## Capabilities

### New Capabilities

- `mail/delivery-input-validation`: Requirements governing how `maildeliver` (and its wrapper `sendmail-local`) MUST validate the recipient address before constructing any filesystem path, and what inputs MUST be rejected.

### Modified Capabilities

<!-- No existing spec-level mail requirements change — the existing mail/spec.md defines delivery semantics but does not specify input validation constraints on the delivery script. -->

## Impact

- `crews/_base/admission/maildeliver` — 2–3 lines added
- `crews/_base/admission/sendmail-local` — 2–3 lines added
- `tests/unit/test_maildeliver.sh` — new shell test file
- No API surface changes; no breaking changes to valid callers

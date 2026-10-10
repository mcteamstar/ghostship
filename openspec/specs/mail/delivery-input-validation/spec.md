# mail/delivery-input-validation Specification

## Purpose
Defines input validation requirements for the `maildeliver` script and its `sendmail-local` wrapper: every recipient address MUST be validated before any filesystem path is constructed from it, preventing path traversal and unexpected mailbox creation.

## Requirements

### Requirement: maildeliver validates recipient BASE before filesystem access
The system SHALL validate that the `BASE` component of a recipient address (derived by stripping the `@` domain and any `+` extension) matches the pattern `^[a-z][a-z0-9_-]*$` before constructing or accessing any filesystem path under `/var/mail/`. If `BASE` does not match this pattern, `maildeliver` SHALL print an error to stderr and exit with status 1 without creating or modifying any files.

#### Scenario: Valid recipient accepted
- **WHEN** `maildeliver ghost@localhost` is called
- **THEN** the message is delivered to `/var/mail/ghost/new/` and `maildeliver` exits 0

#### Scenario: Valid plus-address accepted
- **WHEN** `maildeliver ghost+abc123@localhost` is called
- **THEN** `BASE` resolves to `ghost`, delivery proceeds to `/var/mail/ghost/new/`, and `maildeliver` exits 0

#### Scenario: Path traversal input rejected
- **WHEN** `maildeliver ../../tmp/x@localhost` is called
- **THEN** `maildeliver` emits an error to stderr and exits 1 without creating or writing any file

#### Scenario: Dotted component rejected
- **WHEN** `maildeliver ../etc/passwd@localhost` is called
- **THEN** `maildeliver` emits an error to stderr and exits 1

#### Scenario: Empty BASE rejected
- **WHEN** `maildeliver @localhost` is called (no local part)
- **THEN** `maildeliver` emits an error to stderr and exits 1

#### Scenario: BASE with uppercase rejected
- **WHEN** `maildeliver Ghost@localhost` is called
- **THEN** `maildeliver` emits an error to stderr and exits 1

### Requirement: sendmail-local validates recipients before delegating
The system SHALL apply the same `^[a-z][a-z0-9_-]*$` BASE validation to every recipient in `sendmail-local` before invoking `maildeliver`, providing defense-in-depth. Any recipient whose BASE fails validation SHALL cause `sendmail-local` to emit an error to stderr and exit 1 without delivering to any recipient.

#### Scenario: sendmail-local rejects traversal recipient
- **WHEN** `echo "body" | sendmail-local ../../tmp/evil@localhost` is called
- **THEN** `sendmail-local` exits 1 without invoking `maildeliver` for that address

#### Scenario: sendmail-local accepts valid recipient
- **WHEN** `echo "body" | sendmail-local raven@localhost` is called
- **THEN** `sendmail-local` delegates to `maildeliver raven@localhost` and exits 0

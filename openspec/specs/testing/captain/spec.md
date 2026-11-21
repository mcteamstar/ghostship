# testing/captain Specification

## Purpose

Defines verification coverage for captain behavior.

## Requirements

### Requirement: _append_captain_mail I/O path test coverage
The test suite SHALL exercise `_append_captain_mail` with a mock `container_exec`, covering: signing secret present → signed mail written with valid `X-Admiral-Sig` header; no signing secret → unsigned mail written. Related mailbox read helpers (`_mail_count`, `_read_all_mail_counts`, `_skim_all_mailboxes`) SHALL be tested with mock tar archive responses.

#### Scenario: Captain mail is signed when signing secret is present
- **WHEN** `_append_captain_mail` is called with a crew that has a `signing_secret`
- **THEN** the written mail message contains a valid `X-Admiral-Sig` header

### Requirement: Captain engine behavior has direct unit coverage

Captain unit tests SHALL cover order template resolution and delivery, interval and cron scheduling, reordering, status and mailbox counts, idempotent stop, memory-pressure deferral and escalation, model override, and continuation error handling.

#### Scenario: _check_in_memory_pressure returns correct level
- **WHEN** `_check_in_memory_pressure` is called with a mock podman client reporting
  low available memory
- **THEN** it returns a non-zero pressure level

#### Scenario: _mail_admiral is failure-safe
- **WHEN** `_mail_admiral` is called and the mail delivery raises an exception
- **THEN** the exception is caught and does not propagate to the caller

#### Scenario: _captain_do_status handles stopped crew
- **WHEN** `_captain_do_status` is called for a crew with status "stopped"
- **THEN** it returns without raising and includes status information

#### Scenario: _captain_do_stop is idempotent
- **WHEN** `_captain_do_stop` is called twice on the same crew
- **THEN** the second call does not raise

#### Scenario: do_order delivers mail and updates registry
- **WHEN** `_captain_do_order` is called with a valid standing order
- **THEN** `_append_captain_mail` is called and the registry schedule entry is updated with the new order

#### Scenario: Memory pressure skips dispatch
- **WHEN** `_dispatch_captain_checkin` is called and host memory is below threshold
- **THEN** no spawn call is made and `immediate_dispatch_error` starts with `memory_pressure:`

#### Scenario: Claude backend model override is respected
- **WHEN** `_dispatch_captain_checkin` is called for a crew with `acp_backend="claude"` and a configured default model
- **THEN** the spawn request uses the crew model, not the raven.json model

#### Scenario: _captain_do_order re-order of existing schedule does not duplicate
- **WHEN** `_captain_do_order` is called when a captain entry already exists in the registry
- **THEN** the existing entry is updated, not duplicated

#### Scenario: Continuation handling distinguishes refusal and uncertain acceptance
- **WHEN** a bare HTTP 400, a busy response, a confirmed restore failure, or uncertain acceptance is exercised
- **THEN** tests verify rejection without a second write, preservation of the tracked task, confirmed recovery, and durable hold respectively

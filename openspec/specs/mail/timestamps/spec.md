# mail-timestamps Specification

## Purpose

Surface the `Date` header from Maildir messages alongside subject lines in all mail-reading responses, so the Admiral can tell when a message arrived without reading raw mail files.

## Requirements

### Requirement: Subject listings include received_at per message

Wherever the system returns mail subject lines (in `pickup`, `captain status`, or any other response that lists subjects), each subject entry SHALL be a structured object with `subject` and `received_at` fields rather than a plain string. `received_at` is the ISO 8601 UTC timestamp parsed from the message's `Date` header. If the `Date` header is absent or unparseable, `received_at` SHALL be `null`.

#### Scenario: pickup returns subject with timestamp
- **WHEN** `pickup` is called and the agent mailbox has a message with `Date: Tue, 01 Sep 2026 13:05:00 +0000`
- **THEN** the `agent_subjects` array contains `{"subject": "...", "received_at": "2026-09-01T13:05:00+00:00"}`

#### Scenario: captain status returns subject with timestamp
- **WHEN** `captain(action="status")` is called and the captain mailbox has messages
- **THEN** `captain_subjects` and `admiral_subjects` entries are objects with `subject` and `received_at`

#### Scenario: missing Date header yields null received_at
- **WHEN** a mailbox message has no `Date` header
- **THEN** the corresponding subject entry has `"received_at": null`

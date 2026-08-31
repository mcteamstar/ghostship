## Purpose

Enables the Admiral to read live subject lines from crew mailboxes on both running
and stopped crews, without waking the container, by reading directly from the
container's overlay filesystem via the Podman archive API.

## ADDED Requirements

### Requirement: Captain status returns live mail subjects without waking the crew

`captain(action="status")` SHALL return subject lines from the captain and admiral
mailboxes without starting a stopped crew container. The response SHALL include
`captain_subjects` and `admiral_subjects` arrays alongside the existing mail counts.

#### Scenario: Captain status on stopped crew returns subjects
- **WHEN** `captain(action="status")` is called on a crew whose container is stopped
- **THEN** the response includes `captain_subjects` and `admiral_subjects` with the current subject lines
- **THEN** the crew container remains stopped after the call

#### Scenario: Captain status on running crew returns subjects
- **WHEN** `captain(action="status")` is called on a crew whose container is running
- **THEN** the response includes `captain_subjects` and `admiral_subjects` with live subject lines
- **THEN** the existing mail count fields are still present

#### Scenario: Empty mailbox yields empty subjects list
- **WHEN** `captain(action="status")` is called and a mailbox has no messages
- **THEN** the corresponding subjects array is empty and the mail count is zero

### Requirement: Plain file evac from stopped crew uses archive API directly

`GET /files/{crew_id}/{path}` for a plain file on a stopped crew SHALL use the
Podman archive API directly, without spawning a worker container. The worker
container is used only for git operations (bundle, diff) on stopped crews.

#### Scenario: Plain file evac from stopped crew — no worker spawned
- **WHEN** `evac` is called for a plain (non-bundle, non-diff) file on a stopped crew
- **THEN** the file is returned with HTTP 200
- **THEN** no worker container (`gs-worker-*`) is started or left running

#### Scenario: Git bundle evac from stopped crew still uses worker
- **WHEN** `evac` is called with `bundle=1` on a stopped crew
- **THEN** the bundle is returned via the worker container path (unchanged)

## MODIFIED Requirements

### Requirement: `pickup` surfaces mail subjects for full situational awareness

The system SHALL skim subject lines from relevant mailboxes on every `pickup` call
and include them in the response. This gives the Admiral a mail picture without
needing a separate dispatch.

- When `pickup` is called with a `task_id`: skim the mailbox of the agent that ran
  that task, plus always `/var/mail/raven`. `captain_subjects`, `admiral_subjects`,
  `captain_mail`, and `admiral_mail` are NOT included — use `captain status` for those.
- When `pickup` is called without a `task_id` (crew-wide list): skim all persona
  mailboxes. `captain_subjects`, `admiral_subjects`, `captain_mail`, and `admiral_mail`
  are NOT included — use `captain status` for those.
- Only subject lines are returned — bodies are not read by `pickup`.
- Only unread messages contribute to counts and subject lists. Reading never modifies
  the mailbox files.

#### Scenario: pickup on a specific task returns agent and raven subjects only
- **WHEN** `pickup` is called with a `task_id` for a Ghost task
- **THEN** the response includes `ghost_mail` and `ghost_subjects` plus `raven_mail`
  and `raven_subjects`
- **THEN** the response does NOT include `captain_subjects`, `admiral_subjects`,
  `captain_mail`, or `admiral_mail`

#### Scenario: crew-wide pickup returns persona subjects only
- **WHEN** `pickup` is called without a `task_id`
- **THEN** the response includes subject summaries for persona mailboxes with unread mail
- **THEN** the response does NOT include `captain_subjects`, `admiral_subjects`,
  `captain_mail`, or `admiral_mail`

#### Scenario: empty mailboxes omitted or shown as zero
- **WHEN** `pickup` is called and a mailbox has no unread messages
- **THEN** that mailbox contributes a zero count and an empty subjects list (or is omitted)

#### Scenario: pickup with no unread mail anywhere
- **WHEN** `pickup` is called and all mailboxes are empty
- **THEN** the response is the same shape as today with all mail counts at zero

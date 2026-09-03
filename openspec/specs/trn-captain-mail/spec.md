# trn-captain-mail Specification

## Purpose

Enables the Admiral to read live subject lines from crew mailboxes on both running
and stopped crews, without waking the container, by reading directly from the
container's overlay filesystem via the Podman archive API.

## Requirements

### Requirement: Captain status returns live mail subjects without waking the crew

`captain(action="status")` SHALL return subject lines from the captain and admiral
mailboxes without starting a stopped crew container. The response SHALL include
`captain_subjects` and `admiral_subjects` arrays alongside the existing mail counts.
Each subject entry SHALL be a structured object `{"subject": str, "received_at": str | None}`
where `received_at` is the ISO 8601 UTC timestamp parsed from the message's `Date` header
(see `mail-timestamps` spec). The response SHALL also include `last_checkin_at`
(ISO 8601 UTC) — the wall-clock time the most recent Raven check-in fired for this crew.
`last_checkin_at` SHALL be `null` if no check-in has fired yet.

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

#### Scenario: captain status includes last_checkin_at after a check-in fires
- **WHEN** `captain(action="status")` is called after at least one Raven check-in has run
- **THEN** the response includes `last_checkin_at` as an ISO 8601 UTC string

#### Scenario: captain status last_checkin_at is null before any check-in
- **WHEN** `captain(action="status")` is called on a crew where no check-in has fired
- **THEN** `last_checkin_at` is `null`

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

### Requirement: `pickup` surfaces mail subjects for full situational awareness

The system SHALL skim subject lines from relevant mailboxes on every `pickup` call
and include them in the response. This gives the Admiral a mail picture without
needing a separate dispatch.

- When `pickup` is called with a `task_id`: skim the agent's mailbox, raven, captain,
  and admiral mailboxes. Captain and admiral are read via the archive API (live, works
  on stopped containers).
- When `pickup` is called without a `task_id` (crew-wide list): skim all persona
  mailboxes plus captain and admiral, returned as `agent_subjects`.
- When `pickup` is called without a `task_id` and with an `agent` parameter naming one
  of the six personas, return only that agent's mailbox subjects and count. The task
  list and other mailbox data SHALL NOT be included in this filtered response.
- Only subject lines are returned — bodies are not read by `pickup`.
- Only unread messages contribute to counts and subject lists. Reading never modifies
  the mailbox files.

#### Scenario: pickup on a specific task returns agent, raven, captain, and admiral subjects
- **WHEN** `pickup` is called with a `task_id` for a Ghost task and all mailboxes have unread mail
- **THEN** the response includes `ghost_subjects`, `raven_subjects`, `captain_subjects`, `captain_mail`, `admiral_subjects`, and `admiral_mail`

#### Scenario: crew-wide pickup returns all persona, captain, and admiral subjects
- **WHEN** `pickup` is called without a `task_id`
- **THEN** the response includes `agent_subjects` with subject summaries for all 8 mailboxes (ghost, spectre, banshee, wraith, reaper, raven, captain, admiral), plus `captain_subjects`, `captain_mail`, `admiral_subjects`, and `admiral_mail`

#### Scenario: pickup with agent filter returns single-inbox subjects only
- **WHEN** `pickup` is called without a `task_id` and with `agent="ghost"`
- **THEN** the response includes only ghost's mailbox subjects and count — no task list, no other mailbox data

#### Scenario: pickup with agent filter for an empty mailbox
- **WHEN** `pickup` is called without a `task_id` and with `agent="reaper"` and reaper's mailbox is empty
- **THEN** the response includes `{"agent": "reaper", "subjects": [], "mail": 0}`

#### Scenario: pickup with invalid agent name returns an error
- **WHEN** `pickup` is called with `agent="admiral"` (not a persona mailbox)
- **THEN** the system returns an error indicating the agent name is not valid for this filter

#### Scenario: empty mailboxes omitted or shown as zero
- **WHEN** `pickup` is called and a mailbox has no unread messages
- **THEN** that mailbox contributes a zero count and an empty subjects list (or is omitted)

#### Scenario: pickup with no unread mail anywhere
- **WHEN** `pickup` is called and all mailboxes are empty
- **THEN** the response is the same shape as today with all mail counts at zero

### Requirement: Captain status returns all 8 mailbox subjects

`captain(action="status")` SHALL skim all agent mailboxes — ghost, spectre, banshee,
wraith, reaper, raven, captain, admiral — and return subject lines for each in an
`agent_mail` field. The existing `captain_subjects`, `admiral_subjects`, `captain_mail`,
and `admiral_mail` fields are preserved for backward compatibility.

The broad skim SHALL succeed even when `job_id` is null (dormant captain). If the
crew container is stopped, each mailbox contributes an empty subjects list and zero
count.

#### Scenario: captain status returns all 8 mailbox subject lists
- **WHEN** `captain status` is called for a running crew
- **THEN** the response includes `agent_mail` with keys for ghost, spectre, banshee, wraith, reaper, raven, captain, and admiral, each containing a list of `{"subject": str, "received_at": str|None}` objects

#### Scenario: captain status broad skim works when dormant
- **WHEN** `captain status` is called for a crew with no active cron job (`job_id: null`)
- **THEN** the response still includes `agent_mail` populated from the live mailboxes

#### Scenario: stopped crew returns empty mailbox lists
- **WHEN** `captain status` is called for a crew whose container is stopped
- **THEN** `agent_mail` contains empty lists for all 8 mailboxes

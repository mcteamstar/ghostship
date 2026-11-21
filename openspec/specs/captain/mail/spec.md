# trn-captain-mail Specification

## Purpose

Enables the Admiral to read live subject lines from crew mailboxes on both running
and stopped crews, without waking the container, by reading directly from the
container's overlay filesystem via the Podman archive API.

## Requirements

### Requirement: Captain status returns live mail subjects without waking the crew

`captain(action="status")` SHALL return Captain and Admiral subjects, timestamps, and `last_checkin_at` without starting a stopped crew. Subject entries include `subject` and ISO 8601 UTC `received_at` parsed from `Date`; `last_checkin_at` is the latest Raven check-in time or `null` if none has fired.

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

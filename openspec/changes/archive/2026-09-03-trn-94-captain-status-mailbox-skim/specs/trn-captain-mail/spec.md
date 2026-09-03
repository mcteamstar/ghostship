# trn-captain-mail Specification (delta)

## MODIFIED Requirements

### Modified Requirement: Captain status returns live mail subjects without waking the crew

The existing requirement (captain and admiral mailbox subjects returned by `captain status`) is extended to cover all 8 mailboxes.

`captain status` SHALL skim all agent mailboxes — ghost, spectre, banshee, wraith, reaper, raven, captain, admiral — and return subject lines for each in an `agent_mail` field. The existing `captain_subjects`, `admiral_subjects`, `captain_mail`, and `admiral_mail` fields are preserved for backward compatibility.

The broad skim SHALL succeed even when `job_id` is null (dormant captain). If the crew container is stopped, each mailbox contributes an empty subjects list and zero count.

#### Scenario: captain status returns all 8 mailbox subject lists
- **WHEN** `captain status` is called for a running crew
- **THEN** the response includes `agent_mail` with keys for ghost, spectre, banshee, wraith, reaper, raven, captain, and admiral, each containing a list of `{"subject": str, "received_at": str}` objects

#### Scenario: captain status broad skim works when dormant
- **WHEN** `captain status` is called for a crew with no active cron job (`job_id: null`)
- **THEN** the response still includes `agent_mail` populated from the live mailboxes

#### Scenario: stopped crew returns empty mailbox lists
- **WHEN** `captain status` is called for a crew whose container is stopped
- **THEN** `agent_mail` contains empty lists for all 8 mailboxes

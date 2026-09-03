# task-orchestration Specification (delta)

## MODIFIED Requirements

### Modified Requirement: pickup surfaces mail subjects for full situational awareness

The existing requirement (all crew mailboxes skimmed on crew-level pickup) is extended with an `agent` filter parameter.

When `pickup` is called without a `task_id` and with an optional `agent` parameter naming one of the six personas (ghost, spectre, banshee, wraith, reaper, raven), the system SHALL return only that agent's mailbox subjects and count. The task list and other mailbox data SHALL NOT be included in this filtered response.

When `pickup` is called without a `task_id` and without an `agent` parameter, the existing behaviour applies (all mailboxes, full task list).

#### Scenario: pickup with agent filter returns single-inbox subjects only
- **WHEN** `pickup` is called without a `task_id` and with `agent="ghost"`
- **THEN** the response includes only ghost's mailbox subjects and count — no task list, no other mailbox data

#### Scenario: pickup with agent filter for an empty mailbox
- **WHEN** `pickup` is called without a `task_id` and with `agent="reaper"` and reaper's mailbox is empty
- **THEN** the response includes `{"agent": "reaper", "subjects": [], "mail": 0}`

#### Scenario: pickup with invalid agent name returns an error
- **WHEN** `pickup` is called with `agent="admiral"` (not a persona mailbox)
- **THEN** the system returns an error indicating the agent name is not valid for this filter

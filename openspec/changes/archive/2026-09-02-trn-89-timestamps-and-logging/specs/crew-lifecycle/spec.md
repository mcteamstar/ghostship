# crew-lifecycle Specification (delta)

## MODIFIED Requirements

### Modified Requirement: Crew list response includes timing metadata

The `crews` tool response SHALL include `created_at` (ISO 8601 UTC, from the existing `crews.json` registry entry) and `last_task_at` (ISO 8601 UTC, the most recent time a task was dispatched or completed on this crew) for each crew entry. `last_task_at` SHALL be `null` if no task has been dispatched on this crew.

#### Scenario: crews list includes created_at
- **WHEN** `crews` is called
- **THEN** each entry includes `created_at` derived from the registry

#### Scenario: crews list includes last_task_at after a dispatch
- **WHEN** at least one task has been dispatched on a crew and `crews` is called
- **THEN** that crew's entry includes `last_task_at` as an ISO 8601 UTC string

#### Scenario: crews list last_task_at is null for a newly launched crew
- **WHEN** a crew has been launched but no task has been dispatched
- **THEN** `last_task_at` is `null`

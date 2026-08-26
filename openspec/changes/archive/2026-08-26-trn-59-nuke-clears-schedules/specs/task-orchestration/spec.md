## ADDED Requirements

### Requirement: Schedule registry cleared on confirmed nuke
The transport schedule registry SHALL contain schedule entries only for crews that exist in the crew registry. When a crew is removed via `nuke(confirm=True)`, all entries in that crew's `schedules` list SHALL be removed from the transport registry as part of the same atomic registry write that removes the crew entry itself.

#### Scenario: Registry consistent after nuke
- **WHEN** `nuke(confirm=True)` is called for a crew and the nuke completes successfully
- **THEN** the transport registry contains no `schedules` entries for that crew, and the `_schedule_monitor` loop will not attempt to fire any jobs for the nuked crew in subsequent cycles

#### Scenario: Partial failure does not leave orphan schedule entries
- **WHEN** `nuke(confirm=True)` is called and one or more gateway `DELETE /api/crons/<job_id>` requests fail
- **THEN** the crew's schedule entries are still removed from the transport registry as part of the crew entry deletion — orphaned registry entries are not left behind due to individual gateway cancellation failures

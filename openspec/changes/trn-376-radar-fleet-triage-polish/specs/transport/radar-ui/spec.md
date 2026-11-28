## ADDED Requirements

### Requirement: Readable fleet triage across pane widths
Radar SHALL use neutral treatment for routine stopped crews, make Captain state explicit where shown, and preserve visible text warnings for crews needing attention.

#### Scenario: Fleet is stopped
- **WHEN** crews are routinely stopped
- **THEN** their state is legible without being styled as an error

#### Scenario: Fleet pane is narrow
- **WHEN** the viewport or open inspector reduces the fleet pane width
- **THEN** crew identity, operational state and available actions remain usable without horizontal scrolling
- **AND** omitted secondary data remains reachable in the inspector

### Requirement: Crew snapshot freshness
Radar SHALL show the last successful read time for displayed task and mail snapshots and offer independent refresh for mailbox history and running task snapshots.

#### Scenario: Refresh fails after a successful read
- **WHEN** the operator refreshes a section and the request fails
- **THEN** Radar keeps the previous snapshot and timestamp, shows the failure and offers retry

#### Scenario: Crew changes during refresh
- **WHEN** the operator switches crews while a refresh is pending
- **THEN** its response does not replace the new crew’s data

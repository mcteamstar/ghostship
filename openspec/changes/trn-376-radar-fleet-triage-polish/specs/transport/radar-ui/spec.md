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

## MODIFIED Requirements

### Requirement: Responsive crew inspector
Radar SHALL expose one selected crew at a time in an inspector alongside the fleet on wide screens and in a full-width detail view with Back to fleet on narrower screens. The inspector SHALL preserve access to crew metadata, dashboard, copy ID, tasks, Captain, Mailbox history and Refresh auth. Existing dashboard and credential actions SHALL keep their API contracts. The inspector header SHALL show crew identity, status and available dashboard and copy actions. Messages and Overview SHALL be selectable views. Metadata, tasks, Captain and Refresh auth SHALL remain accessible in Overview.

#### Scenario: Return from a crew on a narrow screen
- **WHEN** an operator opens a crew from a filtered list and returns to the fleet
- **THEN** Radar restores the filter, sort and list scroll position, with any adjustment needed to keep the focused control visible
- **AND** focus returns to the inspected crew control or the filter if that crew is unavailable

#### Scenario: Switch crews during a pending request
- **WHEN** an operator selects a different crew before the previous crew's detail or credential refresh completes
- **THEN** the previous response never populates the current inspector
- **AND** returning to a crew with a pending credential refresh does not allow a duplicate refresh request

#### Scenario: Follow crew history
- **WHEN** an operator opens a valid crew hash directly or navigates with browser Back or Forward
- **THEN** Radar shows the crew identified by the hash or the fleet view when no crew is selected

#### Scenario: A poll removes the selected crew
- **WHEN** a successful fleet response no longer contains the selected crew
- **THEN** Radar clears the selection and informs the operator while preserving the fleet controls


#### Scenario: Browse crews without returning to the list
- **WHEN** the selected crew is in the filtered fleet and another crew is available in the current sort order
- **THEN** previous and next controls move through that sequence without clearing filters or changing the active inspector view
- **AND** the current position and available directions are visible, the crew hash changes, and focus moves to the new crew heading

#### Scenario: Open detail from the fleet
- **WHEN** the operator opens a crew from the fleet with no inspector already open
- **THEN** Radar opens the Messages view and makes Overview available in the same inspector

#### Scenario: Navigate a long crew view on a narrow screen
- **WHEN** the operator scrolls through a crew view with enough viewport height for pinned navigation
- **THEN** Back to fleet and any available previous and next crew controls stay reachable
- **AND** the return-to-heading action moves both scroll and focus to the crew title

### Requirement: Fleet presentation and header
Radar SHALL use a full-width fleet header titled Ghostship Radar and display Ghost Academy fleet totals and freshness there. A phone inspector MAY condense that header while a crew is selected. Fleet connection errors SHALL remain visible. Radar SHALL omit the one-item Fleet sidebar. Gateway health SHALL remain a crew status. List and Cards SHALL share the fleet results and available crew actions. Fleet controls and the result count SHALL sit above the results. List SHALL use a shared set of columns across the Running and Inactive groups when the pane has room for a table. Crew selection, gateway warnings, running task counts, available last-task times and quick actions SHALL remain discoverable in the compact list.

#### Scenario: Switch presentation while inspecting a crew
- **WHEN** an operator switches between List and Cards
- **THEN** search, status filter, sort order and selected crew are preserved
- **AND** crew status, attention cues and available dashboard and copy actions remain accessible


#### Scenario: Scan a long desktop list
- **WHEN** the operator scrolls the fleet results in a desktop pane with room for independent scrolling
- **THEN** fleet controls stay available and the visible table column headings stay aligned with both groups
- **AND** using a dashboard or copy action does not change the selected crew

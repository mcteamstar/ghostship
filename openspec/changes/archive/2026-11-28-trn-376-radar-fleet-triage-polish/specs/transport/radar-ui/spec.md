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

#### Scenario: Open an assigned dashboard
- **WHEN** a stopped crew has an assigned dashboard
- **THEN** Radar labels the action as waking and opening the dashboard and opens the assigned URL in a new tab
- **AND** a crew without an assigned dashboard has no open action and shows its assignment state in Overview

#### Scenario: Open detail from the fleet
- **WHEN** the operator opens a crew from the fleet with no inspector already open
- **THEN** Radar opens the Messages view and makes Overview available in the same inspector

#### Scenario: Navigate a long crew view on a narrow screen
- **WHEN** the operator scrolls through a crew view with enough viewport height for pinned navigation
- **THEN** Back to fleet and any available previous and next crew controls stay reachable
- **AND** the return-to-heading action moves both scroll and focus to the crew title

### Requirement: Fleet presentation and header
Radar SHALL use a full-width fleet header titled Ghostship Radar and display Ghost Academy fleet totals and freshness there. A phone inspector MAY condense that header while a crew is selected. Fleet connection errors SHALL remain visible. Radar SHALL omit the one-item Fleet sidebar. Gateway health SHALL remain a crew status. List and Cards SHALL share the fleet results and available crew actions. Fleet controls and the result count SHALL sit above the results. List SHALL use a shared set of columns across the Active, Asleep and Other groups when the pane has room for a table. Crew selection, gateway warnings, running task counts, available last-task times and quick actions SHALL remain discoverable in the compact list. The Active and Asleep group headings SHALL convey crew state without repeating the same badge on every row. Crew health and Captain warnings SHALL remain visible. Other states SHALL retain their own labels.

#### Scenario: Switch presentation while inspecting a crew
- **WHEN** an operator switches between List and Cards
- **THEN** search, status filter, sort order and selected crew are preserved
- **AND** crew status, attention cues and available dashboard and copy actions remain accessible


#### Scenario: Scan a long desktop list
- **WHEN** the operator scrolls the fleet results in a desktop pane with room for independent scrolling
- **THEN** fleet controls stay available and the visible table column headings stay aligned with both groups
- **AND** using a dashboard or copy action does not change the selected crew

### Requirement: Fleet summary and capacity

Radar SHALL label the running and stopped counts Active and Asleep and show available host memory when reported. If the fleet supplies a maximum active crew count, Radar SHALL include it as the denominator in the Active stat.

#### Scenario: Summary shown
- **WHEN** two crews are running and the fleet reports a maximum of three active crews
- **THEN** the fleet summary shows Active 2 / 3 and a separate Asleep count

#### Scenario: Capacity data absent
- **WHEN** the maximum active crew count or free host memory is absent
- **THEN** Radar shows the plain running count when no maximum is available and omits free memory when absent


### Requirement: Fleet triage controls

Radar SHALL expose search, All, Active, Asleep and Needs attention filters, and the same labeled sort menu in List and Cards at every supported width. Search and status filtering SHALL combine. Active SHALL match running crews and Asleep SHALL match confirmed stopped crews. Other statuses SHALL appear under Other when included in the results. Needs attention SHALL include a running crew with an unhealthy gateway or a crew with a stale enabled Captain using the existing staleness rule. A stopped state alone SHALL NOT count as attention.

#### Scenario: Triage a mixed fleet on a phone
- **WHEN** the operator selects Needs attention, enters a crew ID or comp search and selects a Last Task sort direction at 360 CSS pixels
- **THEN** Radar shows only matching crews with attention signals in the requested sort order within their groups
- **AND** every control is visible and operable without horizontal page scrolling

#### Scenario: No matching crews
- **WHEN** the current filters produce no matches in a populated fleet
- **THEN** Radar explains that no crews match and offers a control to clear filters

#### Scenario: Use the same sort across layouts
- **WHEN** the operator chooses creation order or a last-task direction and switches between List and Cards
- **THEN** the sort menu shows the selected choice and both views apply it within each crew group

### Requirement: Radar preserves existing fleet behavior
Radar SHALL retain the fleet table, grouped crew state, newest-created default ordering, Last Task sort, Captain badges with staleness, gateway warnings, crew detail with tasks and mailbox history, copy crew ID, the `#crew=<id>` deep link, the active crew count in the page title and the last-refreshed time.

#### Scenario: Deep link opens a crew
- **WHEN** an operator loads Radar with `#crew=<id>` for a listed crew
- **THEN** that crew's detail is expanded after the first fleet load

#### Scenario: Ordering and sort unchanged
- **WHEN** the fleet loads with no sort selected
- **THEN** each section lists crews newest created first, and selecting Last Task sort orders each section by last task

#### Scenario: Title and refresh time
- **WHEN** a fleet refresh succeeds
- **THEN** the page title shows `Fleet Radar (N active)` for the current running count and the status area shows the time of the refresh

#### Scenario: Stopped crew gateway warning unchanged
- **WHEN** a stopped crew reports an unreachable gateway
- **THEN** its row appears under Asleep without a gateway warning

### Requirement: Responsive layout
Radar SHALL remain usable at viewport widths down to 360 CSS pixels without horizontal page scrolling, showing each crew's name and expand control, and conveying its state with a group heading or badge, at every width.

#### Scenario: Narrow viewport
- **WHEN** the viewport is 360 CSS pixels wide
- **THEN** the page does not scroll horizontally and every crew shows its name and expand control under its state group, with distinct states labeled where needed

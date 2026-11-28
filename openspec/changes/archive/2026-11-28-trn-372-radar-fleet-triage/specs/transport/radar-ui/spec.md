## ADDED Requirements

### Requirement: Fleet triage controls

Radar SHALL expose search, All, Running, Inactive and Needs attention filters, and a labeled sort control at every supported fleet view width. Search and status filtering SHALL combine. Needs attention SHALL include a running crew with an unhealthy gateway or a crew with a stale enabled Captain using the existing staleness rule. A stopped state alone SHALL NOT count as attention.

#### Scenario: Triage a mixed fleet on a phone
- **WHEN** the operator selects Needs attention, enters a crew ID or comp search and selects a Last Task sort direction at 360 CSS pixels
- **THEN** Radar shows only matching crews with attention signals in the requested sort order within their groups
- **AND** every control is visible and operable without horizontal page scrolling

#### Scenario: No matching crews
- **WHEN** the current filters produce no matches in a populated fleet
- **THEN** Radar explains that no crews match and offers a control to clear filters

### Requirement: Responsive crew inspector

Radar SHALL expose one selected crew at a time in an inspector alongside the fleet on wide screens and in a full-width detail view with Back to fleet on narrower screens. The inspector SHALL preserve access to crew metadata, dashboard, copy ID, tasks, Captain, Mailbox history and Refresh auth. Existing dashboard and credential actions SHALL keep their API contracts.

#### Scenario: Return from a crew on a narrow screen
- **WHEN** an operator opens a crew from a filtered list and returns to the fleet
- **THEN** Radar restores the filter, sort and list scroll position
- **AND** focus returns to the initiating crew control or the filter if that crew is unavailable

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

### Requirement: Fleet presentation and header

Radar SHALL use a full-width header titled Ghostship Radar and display Ghost Academy fleet totals and freshness there. Radar SHALL omit the one-item Fleet sidebar. Gateway health SHALL remain a crew status. List and Cards SHALL share the fleet results and available crew actions.

#### Scenario: Switch presentation while inspecting a crew
- **WHEN** an operator switches between List and Cards
- **THEN** search, status filter, sort order and selected crew are preserved
- **AND** crew status, attention cues and available dashboard and copy actions remain accessible

### Requirement: Crew mailbox history

The crew inspector SHALL show its overview in the panel header and message history in the panel body. The overview SHALL include crew identity, status, available actions and crew metadata. Message history SHALL default to a newest-first timeline and offer grouping by sender or receiving mailbox, with newest first within groups. Each delivery SHALL show its subject, time, sender and recipient when available. The history read SHALL be authenticated as applicable to the portal, scoped to the selected crew, read-only and bounded. It SHALL exclude message bodies and attachments.

#### Scenario: Regroup history
- **WHEN** the operator switches from Time to Sender or Recipient
- **THEN** Radar regroups the same deliveries with consistent ordering and wraps long subjects

#### Scenario: Metadata missing from retained mail
- **WHEN** a delivery has no usable sender, timestamp or subject
- **THEN** Radar labels the missing values, keeps the delivery visible and places undated deliveries after dated ones

#### Scenario: History is unavailable or capped
- **WHEN** the history read fails or reaches its configured limit
- **THEN** Radar distinguishes an unavailable response from an empty mailbox and indicates when a successful snapshot is limited

### Requirement: Fleet freshness stays visible during outages

Radar SHALL keep the last successful refresh time visible beside the fetch error and label stale and critically stale fleet data in text at the existing thresholds. It SHALL announce error and severity transitions without announcing every successful poll.

#### Scenario: Fleet polling fails after a successful refresh
- **WHEN** Radar keeps a successful fleet snapshot after polling fails
- **THEN** the operator can read when the snapshot last refreshed and whether it is stale or critically stale
- **AND** a subsequent successful poll clears the error and stale labels

### Requirement: Mailbox history loads with the selected crew

Radar SHALL load history when a crew is selected, retain it while that crew stays selected and avoid loading history for unselected crews. It SHALL allow retry after failure and prevent results from a previous selection from appearing in the current inspector.

#### Scenario: Inspect a crew
- **WHEN** the operator opens a crew
- **THEN** the inspector shows the overview above its message history
- **AND** one mailbox history request is sent for the selected crew

#### Scenario: Keep the selected history
- **WHEN** the selected crew remains open while the fleet polls
- **THEN** Radar retains the loaded history and grouping without a duplicate read

#### Scenario: Switch crews while history is loading
- **WHEN** the operator switches crews before the history response arrives
- **THEN** Radar cancels the pending read and never renders the previous crew's response in the new inspector

## MODIFIED Requirements

### Requirement: Uplift changes presentation, not content

Radar SHALL show every field and offer every action that the pre-migration UI did, except scheduled jobs, which Radar no longer requests (see "No scheduled-jobs request"). Radar MAY show sender, receiving mailbox and timestamp for mailbox history. Radar SHALL NOT show mail bodies or attachments. Presentation, grouping and layout MAY differ. Radar SHALL NOT request data from a route that no portal route serves.

#### Scenario: Every existing field remains
- **WHEN** a crew detail is open
- **THEN** every item the earlier UI actually displayed (image version, each agent task's agent, ID, done state and elapsed time, Captain schedule, current task and check-in times, mailbox subjects, the Credentials action) is still visible or reachable in the redesigned detail

#### Scenario: No new mailbox data
- **WHEN** mailbox subjects are displayed
- **THEN** Radar shows subjects and allowed history metadata without message bodies or attachments

#### Scenario: No scheduled-jobs request
- **WHEN** an operator opens a running crew's detail
- **THEN** Radar sends no request to `/crews/<id>/api/crons` and shows no Scheduled jobs section

### Requirement: Mailbox subjects are grouped by mailbox

Radar SHALL provide receiving mailbox grouping as an option in history. Each group SHALL show its mailbox name and delivery count. Subjects SHALL wrap.

#### Scenario: Group history by receiving mailbox
- **WHEN** the operator selects Recipient
- **THEN** Radar groups the available deliveries by their receiving mailbox with a count for each group


#### Scenario: Mailboxes with and without subjects
- **WHEN** Recipient grouping includes a populated mailbox and an empty mailbox
- **THEN** both mailbox names and counts remain visible, with “No messages.” for the empty mailbox

#### Scenario: Long subject
- **WHEN** a delivery has a long subject
- **THEN** its subject wraps in the current history view

#### Scenario: Mailboxes cannot be read
- **WHEN** the history read fails
- **THEN** Radar shows a single unavailable state for the crew’s mailbox history

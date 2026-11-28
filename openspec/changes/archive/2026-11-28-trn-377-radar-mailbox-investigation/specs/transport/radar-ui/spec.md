## ADDED Requirements

### Requirement: Readable mailbox delivery metadata
Radar SHALL prioritize the subject, show sender and recipient clearly, and make the full sender address accessible when a shorter label is shown.

#### Scenario: Local address carries a task suffix
- **WHEN** a delivery has a recognized task-qualified local sender
- **THEN** the sender label is concise and the full sender remains available
- **AND** sender grouping preserves distinct addresses

#### Scenario: Timestamp is unavailable
- **WHEN** a delivery has no valid timestamp
- **THEN** the chronological view places it in a clearly labeled undated group after dated deliveries

### Requirement: Search retained mailbox history
Radar SHALL provide case-insensitive search over retained subjects, sender identities and recipients in the selected crew. Radar SHALL allow filtering to a receiving mailbox independently from grouping, apply that scope together with search, and report the count of retained deliveries that match.

#### Scenario: Search with grouping enabled
- **WHEN** the operator searches in any grouping mode
- **THEN** only matching deliveries are shown, with the selected grouping and applicable retention notice

#### Scenario: No deliveries match
- **WHEN** a query produces no matches in a nonempty snapshot
- **THEN** Radar shows a no-match state and lets the operator clear message filters

## MODIFIED Requirements

### Requirement: Crew mailbox history
The crew inspector SHALL show message history in a dedicated Messages view, with crew identity, status and actions available in the shared header. When the desktop inspector has room for independent scrolling, the history controls SHALL remain above the scrolling results and the current group heading SHALL remain visible as its rows scroll. Time, From and To SHALL group deliveries by date, sender and receiving mailbox respectively. The refresh icon SHALL have an accessible name and a visible snapshot time when one is available. Message history SHALL default to a newest-first timeline and offer grouping by sender or receiving mailbox, with newest first within groups. Each delivery SHALL show its subject, time, sender and recipient when available. The history read SHALL be authenticated as applicable to the portal, scoped to the selected crew, read-only and bounded. It SHALL exclude message bodies and attachments.

#### Scenario: Regroup history
- **WHEN** the operator switches from Time to From or To
- **THEN** Radar regroups the same deliveries with consistent ordering and wraps long subjects

#### Scenario: Metadata missing from retained mail
- **WHEN** a delivery has no usable sender, timestamp or subject
- **THEN** Radar labels the missing values, keeps the delivery visible and places undated deliveries after dated ones

#### Scenario: History is unavailable or capped
- **WHEN** the history read fails or reaches its configured limit
- **THEN** Radar distinguishes an unavailable response from an empty mailbox and indicates when a successful snapshot is limited


#### Scenario: Read a long message history
- **WHEN** the operator scrolls mail in the desktop inspector
- **THEN** they can still change search, mailbox scope and grouping or refresh the snapshot
- **AND** they can identify the active date or group without returning to the top

#### Scenario: Jump to a group in the current view
- **WHEN** multiple nonempty groups match the active query and mailbox scope
- **THEN** the operator can choose a date, sender or mailbox according to the current grouping and jump directly to its heading
- **AND** focus moves to that heading in the current view without changing the query, scope or grouping

### Requirement: Mailbox history loads with the selected crew
Radar SHALL load history when a crew is selected, retain it while that crew stays selected and avoid loading history for unselected crews. It SHALL allow retry after failure and prevent results from a previous selection from appearing in the current inspector.

#### Scenario: Inspect a crew
- **WHEN** the operator opens a crew
- **THEN** the inspector opens Messages when entering from the fleet
- **AND** one mailbox history request is sent for the selected crew

#### Scenario: Keep the selected history
- **WHEN** the selected crew remains open while the fleet polls
- **THEN** Radar retains the loaded history and grouping without a duplicate read

#### Scenario: Switch crews while history is loading
- **WHEN** the operator switches crews before the history response arrives
- **THEN** Radar cancels the pending read and never renders the previous crew's response in the new inspector


#### Scenario: Review crew details and return to messages
- **WHEN** the operator switches to Overview and back while the same crew remains selected
- **THEN** the loaded history, search, mailbox scope and grouping remain available without a repeat mail read

### Requirement: Mailbox subjects are grouped by mailbox
Radar SHALL provide receiving mailbox grouping as an option in history. Each group SHALL show its mailbox name and delivery count. Subjects SHALL wrap.

#### Scenario: Group history by receiving mailbox
- **WHEN** the operator selects To
- **THEN** Radar groups the available deliveries by their receiving mailbox with a count for each group

#### Scenario: Mailboxes with and without subjects
- **WHEN** the operator views unfiltered history grouped by receiving mailbox and `captain` holds 2 subjects and `ghost` holds none
- **THEN** the `captain` section shows a count of 2 and both subjects, and the `ghost` section shows `No messages.`

#### Scenario: Long subject
- **WHEN** a subject is 200 characters long
- **THEN** the full subject is readable by wrapping, without horizontal scrolling

#### Scenario: Mailboxes cannot be read
- **WHEN** the history read fails
- **THEN** Radar shows a single unavailable state for the crew’s mailbox history

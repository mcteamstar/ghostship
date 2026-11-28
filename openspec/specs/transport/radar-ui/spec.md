# transport/radar-ui Specification

## Purpose

Defines what an operator sees and can do in the Radar browser UI: the fleet view, crew detail, filtering, refresh and error states, themes, layout and accessibility. It is independent of how the UI is built or served.

## Requirements

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

### Requirement: UI state survives fleet polling

Radar SHALL keep open crew details, loaded detail content, the filter text, the sort selection and scroll position across each five-second fleet refresh and SHALL NOT clear or re-fetch them because new fleet data arrived.

#### Scenario: Open detail across a poll
- **WHEN** a crew detail is open and a fleet refresh completes
- **THEN** the detail stays open with its loaded agents and mailbox subjects, and no new detail request is sent

#### Scenario: Filter across a poll
- **WHEN** the operator has typed a filter and a fleet refresh completes
- **THEN** the filter text and the filtered rows are unchanged

#### Scenario: Polling pause while a detail is open
- **WHEN** a crew detail is open and the last fleet fetch succeeded less than 25 seconds ago
- **THEN** Radar skips the scheduled fleet fetch

### Requirement: Fleet summary and capacity

Radar SHALL label the running and stopped counts Active and Asleep and show available host memory when reported. If the fleet supplies a maximum active crew count, Radar SHALL include it as the denominator in the Active stat.

#### Scenario: Summary shown
- **WHEN** two crews are running and the fleet reports a maximum of three active crews
- **THEN** the fleet summary shows Active 2 / 3 and a separate Asleep count

#### Scenario: Capacity data absent
- **WHEN** the maximum active crew count or free host memory is absent
- **THEN** Radar shows the plain running count when no maximum is available and omits free memory when absent

### Requirement: Crew filter is always available

Radar SHALL show a crew filter at all fleet sizes. It SHALL match crew ID and comp, case-insensitively, and SHALL tell the operator when no crew matches.

#### Scenario: Filter on a small fleet
- **WHEN** the fleet has three crews
- **THEN** the filter input is visible

#### Scenario: Filter matches nothing
- **WHEN** the filter text matches no crew
- **THEN** Radar shows a "no crews match" state and does not show "No crews registered"

### Requirement: Loading, empty, error and stale states

Radar SHALL distinguish first load, an empty fleet, a failed fetch and stale data. It SHALL keep showing the last good data when a later fetch fails and SHALL mark it stale after 15 seconds and critically stale after 30 seconds without a successful fetch.

#### Scenario: First load
- **WHEN** no fleet response has arrived yet
- **THEN** Radar shows a loading state, not an empty-fleet message

#### Scenario: Fetch fails after a success
- **WHEN** a fleet fetch fails after an earlier success
- **THEN** the last data remains visible with an error message, and the stale indicators appear at 15 and 30 seconds

#### Scenario: Transport unreachable
- **WHEN** the fleet fetch returns 502, 503 or 504
- **THEN** the error message says the transport is unreachable

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

### Requirement: Agent tasks are grouped and scannable

Radar SHALL present a crew's agent tasks as cards grouped into running and finished, running first, each card showing the agent name, short task ID, done state and elapsed time. Running tasks SHALL be visually distinct and counted in the group heading, and finished tasks MAY be collapsed behind their count while remaining reachable.

#### Scenario: Mixed running and finished tasks
- **WHEN** a crew has two running tasks and eleven finished tasks
- **THEN** the two running tasks appear first as distinct cards under a "running" heading showing a count of 2, and the finished tasks sit under a heading showing a count of 11

#### Scenario: Finished tasks collapsed
- **WHEN** finished tasks are collapsed
- **THEN** an operator can expand them with the keyboard or pointer and see each task's agent name, short ID and elapsed time

#### Scenario: Unknown agent name
- **WHEN** a task reports an empty agent name
- **THEN** the card shows a neutral "unknown agent" label and the task is still listed

#### Scenario: No active tasks
- **WHEN** a running crew reports no running tasks
- **THEN** Radar shows "No active tasks." as the empty state for the running group

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

### Requirement: Agents and mailbox sections report load failures

Radar SHALL show a loading state for each of the agents and mailbox-subject sections while its request is pending, and an explicit unavailable state when it fails. It SHALL NOT show a failed section as empty, and a failure in one section SHALL NOT change another.

#### Scenario: Agents request fails
- **WHEN** the agents request for an open crew fails
- **THEN** the agents section shows an unavailable state, not "No active tasks"

#### Scenario: One section fails
- **WHEN** the agents request fails while mailbox subjects load
- **THEN** the mailbox section displays its data normally

#### Scenario: Section is genuinely empty
- **WHEN** a request succeeds with no entries
- **THEN** the section shows its empty state, which differs from the unavailable state

### Requirement: Expired session is reported clearly

Radar SHALL detect that a request was redirected to the login page or answered with an HTML page instead of data, and SHALL show a "Session expired, sign in again" state with a link to the login page. It SHALL NOT show a JSON parse error. A response that is empty or has another non-JSON, non-HTML body SHALL be an ordinary request failure, not a session expiry.

#### Scenario: Poll after session expiry
- **WHEN** a fleet poll is redirected to `/dashboard/login`
- **THEN** Radar shows "Session expired, sign in again" with a sign-in link and stops showing parse errors

#### Scenario: Detail fetch after session expiry
- **WHEN** a crew detail request is redirected to the login page
- **THEN** the detail shows the same session-expired state

#### Scenario: Login page served as a 200
- **WHEN** a request is answered with HTTP 200 and an HTML body
- **THEN** Radar shows the session-expired state with a sign-in link

#### Scenario: Empty 200 is not a session expiry
- **WHEN** a request is answered with HTTP 200, no content type and an empty body
- **THEN** Radar treats it as a failed request for that section and does not show "Session expired, sign in again"

### Requirement: Light and dark themes

Radar SHALL render in a light or dark theme following the operating system preference and SHALL keep text and status colours at WCAG AA contrast in both.

#### Scenario: System prefers dark
- **WHEN** the browser reports a dark colour scheme preference
- **THEN** Radar renders with the dark theme without a reload prompt

#### Scenario: Preference changes while open
- **WHEN** the system preference changes while Radar is open
- **THEN** Radar switches theme without a reload

### Requirement: Responsive layout
Radar SHALL remain usable at viewport widths down to 360 CSS pixels without horizontal page scrolling, showing each crew's name and expand control, and conveying its state with a group heading or badge, at every width.

#### Scenario: Narrow viewport
- **WHEN** the viewport is 360 CSS pixels wide
- **THEN** the page does not scroll horizontally and every crew shows its name and expand control under its state group, with distinct states labeled where needed

### Requirement: Keyboard and screen-reader access

Radar SHALL let an operator expand and collapse a crew, copy a crew ID, open a dashboard link and use the filter and sort by keyboard alone. It SHALL expose each control with an accessible name and expansion state, and SHALL announce refresh errors.

#### Scenario: Expand by keyboard
- **WHEN** an operator focuses a crew's expand control and presses Enter or Space
- **THEN** the detail toggles and the control reports its expanded state

#### Scenario: Error announced
- **WHEN** a fleet fetch fails
- **THEN** the error message is exposed in a live region for assistive technology

#### Scenario: Copy by keyboard
- **WHEN** an operator activates the copy control for a crew by keyboard
- **THEN** the crew ID is copied and the control confirms it without expanding the row

### Requirement: Radar preserves the Refresh auth action

Radar SHALL show a Credentials section with a Refresh auth button in each open crew detail. Activating it SHALL send one same-origin `POST /api/crews/{crew_id}/auth/refresh` with no body and SHALL show the returned outcome in that crew's detail.

#### Scenario: Outcome shown with a fixed label
- **WHEN** the refresh response status is `refreshed`, `pending_on_wake`, `current`, `recreate_required`, `credential_missing` or `refresh_failed`
- **THEN** Radar shows that outcome's fixed label and tone, and the transport's guidance message as escaped text, falling back to the outcome's default text when none is sent

#### Scenario: Unrecognised result
- **WHEN** the response is OK but its status is not a known outcome, or its body is not valid JSON
- **THEN** Radar shows "Refresh result unknown" as an error and does not render any response content as markup or style

#### Scenario: One request at a time
- **WHEN** a refresh for a crew is in flight
- **THEN** that crew's button is disabled and marked busy, including after a fleet refresh redraws the table, and activating it again sends no second request

#### Scenario: Outcome kept while the detail stays open
- **WHEN** a refresh finishes and a later fleet refresh arrives while the detail remains open
- **THEN** the outcome stays visible, and it is cleared when the detail is collapsed and reopened

### Requirement: Refresh auth failures are reported distinctly

Radar SHALL tell the operator whether a refresh did not complete because the session expired, Radar rejected the request, the transport was unavailable, or the network failed. It SHALL NOT show any of these as a refresh outcome.

#### Scenario: Session expired during refresh
- **WHEN** the refresh request is redirected to the login page or answered with an HTML page
- **THEN** Radar shows "Session expired" with a sign-in link and nothing is reported as refreshed

#### Scenario: Request rejected or transport unavailable
- **WHEN** the response is 403, or 502, 503 or 504, or another non-OK status
- **THEN** Radar shows "Refresh did not complete" with a reason specific to a same-origin rejection, a transport problem, or an unexpected status

#### Scenario: Network failure
- **WHEN** the request fails before any response arrives
- **THEN** Radar shows "Refresh did not complete" with a network error message and re-enables the button

#### Scenario: No answer within 75 seconds
- **WHEN** a refresh request has received no answer 75 seconds after it was sent
- **THEN** Radar aborts the request and shows "Refresh did not complete: no answer after 75 seconds. It may still finish; check the crew and retry." as a notice that is not one of the six fixed outcomes
- **THEN** the button is re-enabled, and a second refresh may be sent
- **THEN** an answer that arrives after the timeout is ignored and does not change the notice

#### Scenario: Slow refresh is not mistaken for a hang
- **WHEN** a refresh request has been in flight for 10 seconds
- **THEN** the button stays disabled and a "Still working…" note is shown beside it until the request settles, times out or fails

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

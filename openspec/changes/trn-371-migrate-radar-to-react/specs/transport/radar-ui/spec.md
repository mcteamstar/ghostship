# Spec Delta

## Purpose

Defines what an operator sees and can do in the Radar browser UI: the fleet view, crew detail, filtering, refresh and error states, themes, layout and accessibility. It is independent of how the UI is built or served.

## ADDED Requirements

### Requirement: Radar preserves existing fleet behavior

Radar SHALL keep the fleet table, running and inactive sections, default newest-first ordering, Last Task sort, Captain badges with staleness, gateway warnings, crew detail with agents, crons and mailbox subjects, copy-crew-ID, the `#crew=<id>` deep link, the running count in the page title and the last-refreshed time behaving as before the migration.

#### Scenario: Deep link opens a crew
- **WHEN** an operator loads Radar with `#crew=<id>` for a listed crew
- **THEN** that crew's detail is expanded after the first fleet load

#### Scenario: Ordering and sort unchanged
- **WHEN** the fleet loads with no sort selected
- **THEN** each section lists crews newest created first, and selecting Last Task sort orders each section by last task

#### Scenario: Title and refresh time
- **WHEN** a fleet refresh succeeds
- **THEN** the page title shows `Fleet Radar (N running)` for the current running count and the status area shows the time of the refresh

#### Scenario: Stopped crew gateway warning unchanged
- **WHEN** a stopped crew reports an unreachable gateway
- **THEN** its row shows stopped with no gateway warning

### Requirement: UI state survives fleet polling

Radar SHALL keep open crew details, loaded detail content, the filter text, the sort selection and scroll position across each five-second fleet refresh and SHALL NOT clear or re-fetch them because new fleet data arrived.

#### Scenario: Open detail across a poll
- **WHEN** a crew detail is open and a fleet refresh completes
- **THEN** the detail stays open with its loaded agents, crons and mailbox subjects, and no new detail request is sent

#### Scenario: Filter across a poll
- **WHEN** the operator has typed a filter and a fleet refresh completes
- **THEN** the filter text and the filtered rows are unchanged

#### Scenario: Polling pause while a detail is open
- **WHEN** a crew detail is open and the last fleet fetch succeeded less than 25 seconds ago
- **THEN** Radar skips the scheduled fleet fetch

### Requirement: Fleet summary and capacity

Radar SHALL show a summary above the fleet table with the number of running and stopped crews, active crews against the maximum, and free host memory when the fleet response includes them.

#### Scenario: Summary shown
- **WHEN** the fleet response reports running crews, `max_active_crews` and `host_memory_available_gb`
- **THEN** the summary shows the running and stopped counts, active against maximum crews, and free memory

#### Scenario: Capacity data absent
- **WHEN** the fleet response omits `max_active_crews` or `host_memory_available_gb`
- **THEN** the summary omits the missing values and shows no placeholder number for them

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

Radar SHALL show every field and offer every action that the pre-migration UI did, and SHALL NOT show any new data, including mail bodies, senders or timestamps. Presentation, grouping and layout MAY differ.

#### Scenario: Every existing field remains
- **WHEN** a crew detail is open
- **THEN** every item the earlier UI showed (image version, each agent task's agent, ID, done state and elapsed time, Captain schedule, current task and check-in times, scheduled jobs, mailbox subjects, the Credentials action) is still visible or reachable in the redesigned detail

#### Scenario: No new mailbox data
- **WHEN** mailbox subjects are displayed
- **THEN** Radar shows only mailbox names and subject strings

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

Radar SHALL show mailbox subjects as one section per mailbox, named for the mailbox, with the number of subjects, in the same order as today. Long subjects SHALL wrap rather than truncate, and empty mailboxes SHALL stay visible with the explicit text `No messages.`.

#### Scenario: Mailboxes with and without subjects
- **WHEN** `captain` holds 2 subjects and `ghost` holds none
- **THEN** the `captain` section shows a count of 2 and both subjects, and the `ghost` section shows `No messages.`

#### Scenario: Long subject
- **WHEN** a subject is 200 characters long
- **THEN** the full subject is readable by wrapping, without horizontal scrolling

#### Scenario: Mailboxes cannot be read
- **WHEN** the mailbox-subject request fails
- **THEN** Radar shows one unavailable state for all mailboxes and no mailbox as empty

### Requirement: Crew detail sections report load failures

Radar SHALL show a loading state for each of the agents, crons and mailbox-subject sections while its request is pending, and an explicit unavailable state when it fails. It SHALL NOT show a failed section as empty, and a failure in one section SHALL NOT change another.

#### Scenario: Agents request fails
- **WHEN** the agents request for an open crew fails
- **THEN** the agents section shows an unavailable state, not "No active tasks"

#### Scenario: Crons request fails
- **WHEN** the crons request for an open crew fails
- **THEN** the scheduled-jobs section shows an unavailable state and does not hide the section

#### Scenario: One section fails
- **WHEN** the crons request fails while agents and mailbox subjects load
- **THEN** the agents and mailbox sections display their data normally

#### Scenario: Section is genuinely empty
- **WHEN** a request succeeds with no entries
- **THEN** the section shows its empty state, which differs from the unavailable state

### Requirement: Expired session is reported clearly

Radar SHALL detect that a request was redirected to the login page or answered with a non-JSON body instead of data, and SHALL show a "Session expired, sign in again" state with a link to the login page. It SHALL NOT show a JSON parse error.

#### Scenario: Poll after session expiry
- **WHEN** a fleet poll is redirected to `/dashboard/login`
- **THEN** Radar shows "Session expired, sign in again" with a sign-in link and stops showing parse errors

#### Scenario: Detail fetch after session expiry
- **WHEN** a crew detail request is redirected to the login page
- **THEN** the detail shows the same session-expired state

### Requirement: Light and dark themes

Radar SHALL render in a light or dark theme following the operating system preference and SHALL keep text and status colours at WCAG AA contrast in both.

#### Scenario: System prefers dark
- **WHEN** the browser reports a dark colour scheme preference
- **THEN** Radar renders with the dark theme without a reload prompt

#### Scenario: Preference changes while open
- **WHEN** the system preference changes while Radar is open
- **THEN** Radar switches theme without a reload

### Requirement: Responsive layout

Radar SHALL remain usable at viewport widths down to 360 CSS pixels without horizontal page scrolling, showing each crew's name, status and expand control at every width.

#### Scenario: Narrow viewport
- **WHEN** the viewport is 360 CSS pixels wide
- **THEN** the page does not scroll horizontally and every crew shows name, status and an expand control

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

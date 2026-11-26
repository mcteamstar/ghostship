# Spec Delta

## Purpose

Defines what an operator sees and can do in the Radar browser UI: the fleet view, crew detail, filtering, refresh and error states, themes, layout and accessibility. It is independent of how the UI is built or served.

## ADDED Requirements

### Requirement: Radar preserves existing fleet behavior

Radar SHALL keep the fleet table, running and inactive sections, default newest-first ordering, Last Task sort, Captain badges with staleness, gateway warnings, crew detail with agents, crons and mailbox subjects, copy-crew-ID, and `#crew=<id>` deep link behaving as before the migration.

#### Scenario: Deep link opens a crew
- **WHEN** an operator loads Radar with `#crew=<id>` for a listed crew
- **THEN** that crew's detail is expanded after the first fleet load

#### Scenario: Ordering and sort unchanged
- **WHEN** the fleet loads with no sort selected
- **THEN** each section lists crews newest created first, and selecting Last Task sort orders each section by last task

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

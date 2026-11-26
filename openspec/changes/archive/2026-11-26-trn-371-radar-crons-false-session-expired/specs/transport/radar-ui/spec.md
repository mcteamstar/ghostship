# Spec Delta

## MODIFIED Requirements

### Requirement: Radar preserves existing fleet behavior

Radar SHALL keep the fleet table, running and inactive sections, default newest-first ordering, Last Task sort, Captain badges with staleness, gateway warnings, crew detail with agents and mailbox subjects, copy-crew-ID, the `#crew=<id>` deep link, the running count in the page title and the last-refreshed time behaving as before the migration.

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
- **THEN** the detail stays open with its loaded agents and mailbox subjects, and no new detail request is sent

#### Scenario: Filter across a poll
- **WHEN** the operator has typed a filter and a fleet refresh completes
- **THEN** the filter text and the filtered rows are unchanged

#### Scenario: Polling pause while a detail is open
- **WHEN** a crew detail is open and the last fleet fetch succeeded less than 25 seconds ago
- **THEN** Radar skips the scheduled fleet fetch

### Requirement: Uplift changes presentation, not content

Radar SHALL show every field and offer every action that the pre-migration UI did, except scheduled jobs, which Radar no longer requests (see "No scheduled-jobs request"). Radar SHALL NOT show any new data, including mail bodies, senders or timestamps. Presentation, grouping and layout MAY differ. Radar SHALL NOT request data from a route that no portal route serves.

#### Scenario: Every existing field remains
- **WHEN** a crew detail is open
- **THEN** every item the earlier UI actually displayed (image version, each agent task's agent, ID, done state and elapsed time, Captain schedule, current task and check-in times, mailbox subjects, the Credentials action) is still visible or reachable in the redesigned detail

#### Scenario: No new mailbox data
- **WHEN** mailbox subjects are displayed
- **THEN** Radar shows only mailbox names and subject strings

#### Scenario: No scheduled-jobs request
- **WHEN** an operator opens a running crew's detail
- **THEN** Radar sends no request to `/crews/<id>/api/crons` and shows no Scheduled jobs section

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

## REMOVED Requirements

### Requirement: Crew detail sections report load failures
**Reason**: The Scheduled jobs section is removed because the `/crews/<id>/api/crons` route it reads has no portal route and never returned data. The load-failure behavior for the agents and mailbox-subject sections continues under a renamed requirement.
**Migration**: See "Agents and mailbox sections report load failures", which keeps the agents and mailbox scenarios and drops the scheduled-jobs ones.

## ADDED Requirements

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

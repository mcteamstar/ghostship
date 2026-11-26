# Spec Delta

## MODIFIED Requirements

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

### Requirement: Crew detail sections report load failures

Radar SHALL show a loading state for each of the agents, crons and mailbox-subject sections while its request is pending, and an explicit unavailable state when it fails. It SHALL NOT show a failed section as empty, and a failure in one section SHALL NOT change another. For a crew with no dashboard URL, Radar SHALL NOT request scheduled jobs and SHALL NOT show the Scheduled jobs section.

#### Scenario: Agents request fails
- **WHEN** the agents request for an open crew fails
- **THEN** the agents section shows an unavailable state, not "No active tasks"

#### Scenario: Crons request fails
- **WHEN** the crons request for an open running crew that has a dashboard URL fails
- **THEN** the scheduled-jobs section shows an unavailable state and does not hide the section

#### Scenario: Crew without a dashboard
- **WHEN** an operator opens a running crew whose dashboard URL is absent
- **THEN** Radar sends no scheduled-jobs request and shows no Scheduled jobs section, and no session-expired notice appears

#### Scenario: One section fails
- **WHEN** the crons request fails while agents and mailbox subjects load
- **THEN** the agents and mailbox sections display their data normally

#### Scenario: Section is genuinely empty
- **WHEN** a request succeeds with no entries
- **THEN** the section shows its empty state, which differs from the unavailable state

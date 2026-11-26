# ga-radar Specification

## Purpose

`ga-radar` is a dedicated microservice container on `ga-portside` that owns the
Radar fleet dashboard SPA and its browser-facing API. It is the only entry point
for UI traffic — browsers never reach `ga-transport` directly for fleet
observability.

## Requirements

### Requirement: ga-radar runs as a dedicated portside container

`ga-radar` SHALL run as a standalone container on `ga-portside` only. It SHALL
NOT be on `ga-starboard`. It SHALL expose port `8080` internally with no host port
published and no data volume.

Image: `localhost/ga-radar:latest`, built from `radar/Containerfile`.

#### Scenario: Container network isolation

- **WHEN** `ga-radar` is started by `ghostship upgrade`
- **THEN** it is attached to `ga-portside` only
- **THEN** crew containers on `ga-starboard` cannot reach it by hostname

### Requirement: ga-radar serves the Radar SPA and fleet API

`ga-radar` SHALL serve the SPA and static assets, proxy fleet and per-crew agent data to `ga-transport`, and expose unauthenticated `/health`. Static ES modules SHALL be baked into the image; the SPA polls fleet data every five seconds and fetches live tasks when a row expands.

#### Scenario: SPA served at root

- **WHEN** `GET /` is requested through Caddy with a valid session
- **THEN** `ga-radar` returns HTTP 200 with `Content-Type: text/html`
- **THEN** the response body is `static/index.html`

#### Scenario: Static assets served

- **WHEN** `GET /static/main.js` or `GET /static/style.css` is requested
- **THEN** `ga-radar` returns the asset with the correct content-type

#### Scenario: Fleet API proxied to transport

- **WHEN** `GET /api/crews` is requested
- **THEN** `ga-radar` calls `GET http://ga-transport:64057/internal/crews` with `X-Transport-Token`
- **THEN** the response payload is returned to the browser unchanged

#### Scenario: Per-crew agents endpoint proxied to transport

- **WHEN** `GET /api/crews/{crew_id}/agents` is requested with a valid session
- **THEN** `ga-radar` calls `GET http://ga-transport:64057/internal/crews/{crew_id}/agents` with `X-Transport-Token`
- **THEN** the response `{"agents": [...]}` is returned to the browser
- **THEN** if the crew is stopped or gateway unreachable, `{"agents": []}` is returned with HTTP 200

#### Scenario: Health endpoint needs no auth

- **WHEN** `GET /health` is requested without any credentials
- **THEN** `ga-radar` returns HTTP 200 `{"status": "ok"}`

### Requirement: ga-radar authenticates to ga-transport with the shared secret

At startup, `ga-radar` SHALL read `/run/secrets/ga-transport-secret` and send it as `X-Transport-Token` to the transport. If absent, it SHALL start with an empty token and log a warning. `TRANSPORT_URL` supplies the transport base URL.

#### Scenario: Secret absent at startup

- **WHEN** `/run/secrets/ga-transport-secret` does not exist
- **THEN** `ga-radar` starts successfully and logs a warning
- **THEN** requests to `/api/crews` return 502 (transport rejects the empty token)

### Requirement: Caddy routes browser traffic to ga-radar

Caddy (`ga-portal`) SHALL route `GET /`, `GET /api/crews*`, and `GET /static/*`
to `ga-radar:8080` via `reverse_proxy`. Session gating (`forward_auth`,
`/dashboard/login` redirect on 401) is unchanged — it runs at the Caddy layer
before the proxy.

#### Scenario: Unauthenticated request redirected to login

- **WHEN** `GET /` is requested without a valid `gs_session` cookie and `GA_API_KEY` is set
- **THEN** Caddy redirects the browser to `/dashboard/login?next=/`

#### Scenario: Authenticated request served by ga-radar

- **WHEN** `GET /` is requested with a valid `gs_session` cookie
- **THEN** Caddy proxies the request to `ga-radar:8080/`
- **THEN** the Radar SPA HTML is returned

### Requirement: ga-transport exposes per-crew agents endpoint

`ga-transport` SHALL expose `GET /internal/crews/{crew_id}/agents` (portside-internal, requires `X-Transport-Token`). It SHALL query the crew's KiroCrew gateway at `GET /api/tasks` with a 5-second timeout. It SHALL return `{"agents": [...]}` where each entry has `task_id`, `agent`, `done`, `elapsed_secs`. If the crew is not running or the gateway is unreachable, it SHALL return `{"agents": []}` with HTTP 200.

#### Scenario: Running crew returns live task list

- **WHEN** `GET /internal/crews/{crew_id}/agents` is requested for a running crew
- **THEN** transport queries the crew gateway at `GET /api/tasks`
- **THEN** the mapped task list is returned as `{"agents": [...]}`

#### Scenario: Stopped or unreachable crew returns empty agents

- **WHEN** `GET /internal/crews/{crew_id}/agents` is requested for a stopped crew or a crew whose gateway is unreachable
- **THEN** transport returns `{"agents": []}` with HTTP 200

### Requirement: Gateway health warnings account for crew state

Radar SHALL show stopped crews as stopped without an unreachable gateway warning. It SHALL continue to show a gateway warning for a running crew whose gateway is unhealthy.

#### Scenario: Stopped crew
- **WHEN** a stopped crew reports an unreachable gateway
- **THEN** its row shows stopped without a gateway warning

#### Scenario: Running crew with unhealthy gateway
- **WHEN** a running crew reports an unreachable gateway
- **THEN** its row shows the gateway warning

#### Scenario: Running crew with healthy gateway
- **WHEN** a running crew reports a healthy gateway
- **THEN** its row has no gateway warning

### Requirement: Default fleet ordering

Radar SHALL order crews by creation time, newest first, within each running and inactive section by default. Crews without a valid creation time SHALL appear after those with valid creation times. The Last Task sort control SHALL continue to work.

#### Scenario: Multiple crews in a section
- **WHEN** the fleet table has no Last Task sort selected
- **THEN** each section shows the most recently created crews first

#### Scenario: Last Task sort selected
- **WHEN** the user selects the Last Task sort
- **THEN** the selected Last Task ordering applies within each section

### Requirement: Radar shows crew mailbox subjects
Radar SHALL show subject strings grouped by mailbox in a crew's expanded detail. It SHALL fetch them on demand and SHALL expose no message bodies or message metadata beyond mailbox names and subjects.

#### Scenario: Subjects are loaded when crew detail opens
- **WHEN** an operator expands a registered crew's detail
- **THEN** Radar fetches and displays subjects from `ghost`, `spectre`, `banshee`, `wraith`, `reaper`, `raven`, `captain`, and `admiral` without adding mailbox reads to the fleet polling request

#### Scenario: Subjects remain available for stopped crews
- **WHEN** an operator expands a stopped crew's detail and its mailbox files are readable
- **THEN** Radar displays the same mailbox subjects available for a running crew
- **THEN** reading the subjects does not alter or consume any mailbox messages

#### Scenario: Empty mailbox
- **WHEN** a crew mailbox has no messages with a subject
- **THEN** Radar displays an explicit empty state for that mailbox

#### Scenario: Mailbox subjects cannot be loaded
- **WHEN** the mailbox-subject request fails
- **THEN** Radar displays a single unavailable state for the crew's mailboxes without presenting any mailbox as empty

#### Scenario: Browser request requires the Portal session
- **WHEN** an unauthenticated browser requests crew mailbox subjects while API-key authentication is enabled
- **THEN** the existing Portal session gate prevents the request from reaching Radar and no mailbox data is returned

### Requirement: Transport provides a protected subject-only mailbox endpoint
Transport SHALL expose a portside-internal, transport-secret-protected endpoint that returns each registered crew's mailbox names and subject strings only. It SHALL leave mailbox messages unchanged.

#### Scenario: Read subjects from a registered crew
- **WHEN** Radar requests a registered crew's mailbox subjects with a valid `X-Transport-Token`
- **THEN** Transport returns `ghost`, `spectre`, `banshee`, `wraith`, `reaper`, `raven`, `captain`, and `admiral`, each mapped to a list of subject strings
- **THEN** the response contains no message bodies, sender details, timestamps, or separate count fields

#### Scenario: Subjects are ordered and bounded
- **WHEN** a mailbox holds more than 50 messages with subjects
- **THEN** Transport returns that mailbox's 50 most recently delivered subjects, newest first
- **THEN** each subject is at most 200 characters

#### Scenario: Mailbox has never been created
- **WHEN** a registered crew has no directory or file for one of the eight mailboxes (for example, a stopped crew that has never received `admiral` mail)
- **THEN** Transport returns an empty list for that mailbox and does not report the crew's mailboxes as unavailable

#### Scenario: Registered crew's container no longer exists
- **WHEN** Radar requests subjects for a registered crew whose container has been removed
- **THEN** Transport returns an error response that Radar can display as unavailable, and does not return empty mailboxes

#### Scenario: Read subjects for a stopped crew
- **WHEN** Radar requests subjects for a registered stopped crew with a valid `X-Transport-Token`
- **THEN** Transport returns subjects from readable mailbox files without starting the crew

#### Scenario: Unknown crew
- **WHEN** Radar requests mailbox subjects for an unregistered crew
- **THEN** Transport returns HTTP 404

#### Scenario: Missing or invalid transport secret
- **WHEN** a request omits or supplies an invalid `X-Transport-Token`
- **THEN** Transport rejects the request without returning mailbox data

#### Scenario: Mailbox source is unavailable
- **WHEN** Transport cannot read any existing mailbox of a registered crew, or cannot reach the crew's container filesystem
- **THEN** Transport returns an error response for the whole request that Radar can display as unavailable, rather than reporting any mailbox as empty or returning a partial result

### Requirement: Radar exposes the crew auth refresh operation
Radar SHALL provide an operator action for each crew and a browser-facing `POST /api/crews/{crew_id}/auth/refresh` endpoint. The endpoint SHALL proxy to the transport's internal refresh API using `X-Transport-Token` and return the transport outcome without modification.

#### Scenario: Operator refreshes auth from a crew detail panel
- **WHEN** an operator selects the auth refresh action for a crew in Radar
- **THEN** the browser calls `POST /api/crews/{crew_id}/auth/refresh` and Radar proxies it to `POST /internal/crews/{crew_id}/auth/refresh`
- **THEN** Radar displays the returned outcome, including pending-on-wake or recreate-required guidance

#### Scenario: Transport is unavailable during refresh
- **WHEN** Radar cannot reach the transport while proxying a refresh request
- **THEN** Radar returns HTTP 502 with a safe transport-unavailable message and displays that refresh did not complete

#### Scenario: Cross-origin or missing Origin is rejected
- **WHEN** `POST /api/crews/{crew_id}/auth/refresh` reaches Radar without an `Origin` header, or with an `Origin` that does not match the request host
- **THEN** Radar returns HTTP 403 and does not call the transport

#### Scenario: Portal session expires before refresh
- **WHEN** the operator selects the refresh action after the portal session has expired and Caddy responds with a redirect to `/dashboard/login`
- **THEN** Radar's UI tells the operator to sign in again and does not display a refresh outcome

### Requirement: Portal session gates the Radar auth refresh action
Caddy SHALL route `POST /api/crews/{crew_id}/auth/refresh` through the existing Radar session gate. When API-key auth is configured, the browser action SHALL require a valid `gs_session` cookie.

#### Scenario: Authenticated portal operator refreshes a crew
- **WHEN** a valid portal session calls `POST /api/crews/{crew_id}/auth/refresh`
- **THEN** Caddy forwards the request to Radar

#### Scenario: Unauthenticated portal request
- **WHEN** the refresh action is requested without a valid portal session and API-key auth is configured
- **THEN** Caddy redirects the browser to `/dashboard/login` and does not forward the request to Radar

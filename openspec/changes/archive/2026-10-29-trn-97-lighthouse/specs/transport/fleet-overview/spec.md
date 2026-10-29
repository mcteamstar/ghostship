## Purpose

Serves a read-only fleet observability dashboard at `/` on the ghostship transport,
giving operators a browser view of all crews, their status, active tasks, and
captain state without requiring an active MCP agent session.

## ADDED Requirements

### Requirement: `GET /` serves the Lighthouse fleet dashboard

The transport SHALL handle `GET /` and return an HTML response containing the
Lighthouse SPA. The route SHALL be session-gated via the existing `DashboardGate`
mechanism — the same `gs_session` cookie used to access the per-crew KC dashboards.
Caddy's `forward_auth` handler validates the session before proxying to the
transport. An unauthenticated request SHALL be redirected to
`/dashboard/login?next=/`.

In `BearerAuthMiddleware`, `GET /` SHALL be listed in `public_routes` — session
enforcement is at the Caddy layer via `forward_auth`, not at the transport bearer
layer, exactly as for `/crews/*/ui`.

#### Scenario: Authenticated request returns Lighthouse HTML
- **WHEN** `GET /` is requested with a valid `gs_session` cookie
- **THEN** Caddy's `forward_auth` check passes and the transport returns HTTP 200
  with `Content-Type: text/html`
- **THEN** the response body is the Lighthouse SPA HTML

#### Scenario: Unauthenticated request is redirected to login
- **WHEN** `GET /` is requested without a valid `gs_session` cookie
- **THEN** Caddy's `forward_auth` call to `/dashboard/auth` returns a redirect
- **THEN** the browser is redirected to `/dashboard/login?next=/`

#### Scenario: After login, browser is returned to Lighthouse
- **WHEN** an operator successfully authenticates at `/dashboard/login?next=/`
- **THEN** the browser is redirected back to `/` with a valid `gs_session` cookie
- **THEN** the Lighthouse SPA loads

### Requirement: Fleet dashboard polls the transport for data

The Lighthouse SPA SHALL poll `GET /api/crews` at a fixed interval (≤ 10 s) to
refresh the fleet view. All `fetch()` calls from the SPA SHALL use the browser's
`gs_session` cookie automatically (same-origin requests with `credentials:
"include"`). The SPA SHALL NOT require any explicit token or credential management
in JavaScript.

#### Scenario: SPA refreshes fleet data automatically
- **WHEN** the Lighthouse page is open in a browser with a valid `gs_session` cookie
- **THEN** the SPA issues `GET /api/crews` at most every 10 s with the session cookie
- **THEN** the fleet table updates to reflect the latest response

### Requirement: Per-crew detail fetched from the crew API proxy

The SPA MAY fetch per-crew detail by calling `GET /crews/{crew_id}/api/{path}` on
the same origin. Useful paths include `/api/spawn` (tasks), `/api/crons`
(schedule/captain state), and `/api/mailboxes` (mail summary). These paths are
proxied by the existing crew API proxy — no new proxy routes are needed.

#### Scenario: Expanding a crew row fetches task and captain state
- **WHEN** the operator expands a crew row in the Lighthouse UI
- **THEN** the SPA issues one or more `GET /crews/{crew_id}/api/*` requests
- **THEN** the response data is displayed in the expanded panel

### Requirement: Link to per-crew KC dashboard

When a crew entry in `/api/crews` includes a non-null `dashboard_url`, the
Lighthouse SPA SHALL render a link that opens the per-crew KC dashboard in a new
browser tab.

#### Scenario: Crew with dashboard_url shows a link
- **WHEN** a crew's entry in `/api/crews` has a non-null `dashboard_url`
- **THEN** the Lighthouse table row includes a link targeting that URL
- **THEN** clicking the link opens it in a new tab

#### Scenario: Crew without dashboard_url shows no link
- **WHEN** a crew's entry in `/api/crews` has `dashboard_url: null`
- **THEN** no dashboard link is rendered for that row

### Requirement: Lighthouse is read-only in this change

The Lighthouse SPA SHALL NOT expose controls for launching, nuking, dispatching, or
steering crews in this version. All interactions are GET requests only.

#### Scenario: No write actions available
- **WHEN** the Lighthouse page is loaded
- **THEN** no form submission, dispatch button, or destructive action control is present

# transport/fleet-overview Specification

## Purpose

Serves a read-only fleet observability dashboard at `/` on the ghostship transport,
giving operators a browser view of all crews, their status, active tasks, and
captain state without requiring an active MCP agent session.

## Requirements

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

Active agent data is sourced from the fleet payload (`agents` array per crew) to
avoid an extra fetch per row. Per-crew cron/schedule data is fetched from
`/crews/{crew_id}/api/crons` only when the operator expands a row and the crew is
running. For stopped crews, a message is shown explaining that live schedule data
is unavailable.

#### Scenario: Expanding a crew row shows agent and captain state
- **WHEN** the operator expands a crew row in the Lighthouse UI
- **THEN** the SPA renders active tasks from the fleet payload agents array
- **THEN** captain state (enabled/paused, schedule, current task) is rendered
  from the `captain` field in the fleet payload
- **THEN** for running crews, non-captain scheduled jobs are fetched from
  `/crews/{crew_id}/api/crons` and appended

#### Scenario: Stopped crew detail shows appropriate message
- **WHEN** the operator expands a stopped crew row
- **THEN** task and captain state from the registry are shown (no gateway probe)
- **THEN** a message indicates live schedule data is unavailable

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

### Requirement: Fleet table shows crew busyness at a glance

The Lighthouse SPA SHALL surface per-crew activity state in the fleet table without
requiring row expansion. The crew name cell SHALL show:
- An "N active" badge (cyan) when the crew has active (not-done) agent tasks
- A captain state badge ("⚑ captain" in purple when active, "⚑ paused" in muted
  when paused) when the crew has a captain schedule entry

Stopped crews SHALL be visually de-emphasised (reduced opacity). The `running`
status badge SHALL use a subtle green glow to distinguish live crews. Uptime SHALL
show `—` for stopped crews.

#### Scenario: Active crew shows task count and captain badge
- **WHEN** a crew has active (not-done) agent tasks and an active captain
- **THEN** the crew name cell shows a cyan "N active" badge and a purple "⚑ captain" badge

#### Scenario: Paused captain shown distinctly
- **WHEN** a crew's captain schedule exists but is disabled
- **THEN** a muted "⚑ paused" badge is shown in the crew name cell

#### Scenario: Stopped crew is de-emphasised
- **WHEN** a crew has status "stopped"
- **THEN** the row is rendered at reduced opacity and uptime shows "—"

### Requirement: Click affordance and expandable row detail

Each data row in the fleet table SHALL show a `▸` indicator in the crew name cell
to signal it is clickable. Clicking the row toggles an expanded detail panel showing
active tasks and captain/schedule state. The expanded state SHALL be preserved across
5-second poll refreshes — the panel does not collapse on re-render.

#### Scenario: Row expand and collapse
- **WHEN** the operator clicks a crew row
- **THEN** a detail panel appears beneath the row with active tasks and captain state
- **THEN** clicking the row again collapses the detail panel
- **THEN** the indicator changes from `▸` to `▾` when expanded

#### Scenario: Open rows survive poll refresh
- **WHEN** a row is expanded and the 5 s poll fires
- **THEN** the detail panel remains open after the re-render

### Requirement: Relative timestamps

The "Last Task" column SHALL display timestamps as human-readable relative strings
("just now", "3m ago", "2h ago", "4d ago") rather than absolute datetime strings.

#### Scenario: Recent timestamp shown as relative
- **WHEN** `last_task_at` is 90 seconds ago
- **THEN** the cell shows "1m ago"

### Requirement: CSP-compliant inline SPA

The Lighthouse SPA HTML returned by `GET /` SHALL comply with the transport's
nonce-based Content Security Policy. The handler SHALL inject the per-request
`csp_nonce` (from `request.scope["csp_nonce"]`) into the `<style>` and `<script>`
nonce attributes. No inline `style=` attributes SHALL be used in JS-generated HTML;
all dynamic styling SHALL use CSS classes.

#### Scenario: No CSP violations on page load
- **WHEN** `GET /` is loaded in a browser with the transport's CSP headers active
- **THEN** no Content Security Policy violations are reported in the browser console

### Requirement: Ghostship brand theme

The Lighthouse SPA SHALL use a visual theme consistent with the Ghostship brand:
deep space / cosmic nebula aesthetic with a dark background, CSS starfield, nebula
glow gradients, ghost emoji header, and per-role colour accents (teal for active
tasks, purple for captain/Raven, green glow for running status).

#### Scenario: Page loads with cosmic theme
- **WHEN** `GET /` is loaded
- **THEN** the page has a deep space dark background with subtle nebula glow
- **THEN** the header shows the 👻 ghost emoji with a pulsing purple/teal glow

### Requirement: Lighthouse is read-only in this change

The Lighthouse SPA SHALL NOT expose controls for launching, nuking, dispatching, or
steering crews in this version. All interactions are GET requests only.

#### Scenario: No write actions available
- **WHEN** the Lighthouse page is loaded
- **THEN** no form submission, dispatch button, or destructive action control is present

# transport/fleet-overview Specification

## Purpose

Serves a read-only fleet observability dashboard at `/` on the ghostship transport,
giving operators a browser view of all crews, their status, active tasks, and
captain state without requiring an active MCP agent session.

## Requirements

### Requirement: Gateway health field in crews() output
The `crews()` tool SHALL include a `gateway_healthy: bool` field in each crew entry, reflecting whether the gateway liveness probe succeeded at the time of the call.

#### Scenario: Healthy gateway
- **WHEN** `crews()` is called and a crew's container is running and its gateway responds to the liveness probe
- **THEN** that crew's entry includes `gateway_healthy: true`

#### Scenario: Unresponsive gateway
- **WHEN** `crews()` is called and a crew's container is running but its gateway does not respond to the liveness probe
- **THEN** that crew's entry includes `gateway_healthy: false`

#### Scenario: Stopped container
- **WHEN** `crews()` is called and a crew's container is stopped
- **THEN** that crew's entry includes `gateway_healthy: false`

### Requirement: crews() includes crew image version
The `crews()` tool SHALL include a `crew_image_version` field in each crew entry, reflecting the version of the crew image that crew was built from. The value SHALL be sourced from the registry, populated at launch time.

#### Scenario: crews() shows version for a running crew
- **WHEN** `crews()` is called and a crew has `crew_image_version` stored in the registry
- **THEN** the crew entry includes `crew_image_version` with the stored semver string

#### Scenario: crews() for a crew launched before version tracking
- **WHEN** `crews()` is called and a crew's registry entry has no `crew_image_version` field
- **THEN** the crew entry includes `crew_image_version` set to `"unknown"`

### Requirement: Crew list response includes timing metadata

The `crews` tool response SHALL include `created_at` (ISO 8601 UTC, from the existing `crews.json` registry entry) and `last_task_at` (ISO 8601 UTC, the most recent time a task was dispatched on this crew) for each crew entry. `last_task_at` SHALL be `null` if no task has been dispatched on this crew.

#### Scenario: crews list includes created_at
- **WHEN** `crews` is called
- **THEN** each entry includes `created_at` derived from the registry

#### Scenario: crews list includes last_task_at after a dispatch
- **WHEN** at least one task has been dispatched on a crew and `crews` is called
- **THEN** that crew's entry includes `last_task_at` as an ISO 8601 UTC string

#### Scenario: crews list last_task_at is null for a newly launched crew
- **WHEN** a crew has been launched but no task has been dispatched
- **THEN** `last_task_at` is `null`

### Requirement: crews() active_crews reflects actual Podman state

`crews()` SHALL count only registry-running crews confirmed running by Podman. It SHALL report stale entries as stopped and correct their registry status.

#### Scenario: Registry-running crew whose container is actually running
- **WHEN** `crews()` is called and a crew has `status: "running"` in the registry
  and its Podman container is confirmed running
- **THEN** that crew appears with `status: "running"` and is counted in `active_crews`

#### Scenario: Registry-running crew whose container is externally stopped
- **WHEN** `crews()` is called and a crew has `status: "running"` in the registry
  but its Podman container is not running
- **THEN** that crew appears with `status: "stopped"` in the response, is NOT
  counted in `active_crews`, and the registry entry is corrected to `"stopped"`

#### Scenario: active_crews matches confirmed running container count
- **WHEN** `crews()` is called after one or more crew containers have been
  stopped outside ghostship (e.g. via `podman stop` or a VM reboot)
- **THEN** `active_crews` equals the number of containers that are actually
  running in Podman, not the number of registry entries with `status: "running"`

### Requirement: Crew listing
The system SHALL list every registered crew with its status, creation time, and active agent tasks.

#### Scenario: List crews with a mix of states
- **WHEN** `crews` is called while some crews are running and others are stopped or idle
- **THEN** the system returns an entry per crew with its known metadata, and an empty `agents` list for any crew whose gateway cannot currently be reached

### Requirement: `GET /` serves the Radar fleet dashboard

`GET /` SHALL serve the Radar SPA behind Caddy `forward_auth`; unauthenticated users SHALL be redirected to `/dashboard/login?next=/`. The transport bearer middleware SHALL keep `/` public, with session enforcement at Caddy as for `/crews/*/ui`.

#### Scenario: Authenticated request returns Radar HTML
- **WHEN** `GET /` is requested with a valid `gs_session` cookie
- **THEN** Caddy's `forward_auth` check passes and the transport returns HTTP 200
  with `Content-Type: text/html`
- **THEN** the response body is the Radar SPA HTML

#### Scenario: Unauthenticated request is redirected to login
- **WHEN** `GET /` is requested without a valid `gs_session` cookie
- **THEN** Caddy's `forward_auth` call to `/dashboard/auth` returns a redirect
- **THEN** the browser is redirected to `/dashboard/login?next=/`

#### Scenario: After login, browser is returned to Radar
- **WHEN** an operator successfully authenticates at `/dashboard/login?next=/`
- **THEN** the browser is redirected back to `/` with a valid `gs_session` cookie
- **THEN** the Radar SPA loads

### Requirement: Fleet dashboard polls the transport for data

The Radar SPA SHALL poll `GET /api/crews` at a fixed interval (≤ 10 s) to
refresh the fleet view. All `fetch()` calls from the SPA SHALL use the browser's
`gs_session` cookie automatically (same-origin requests with `credentials:
"include"`). The SPA SHALL NOT require any explicit token or credential management
in JavaScript.

#### Scenario: SPA refreshes fleet data automatically
- **WHEN** the Radar page is open in a browser with a valid `gs_session` cookie
- **THEN** the SPA issues `GET /api/crews` at most every 10 s with the session cookie
- **THEN** the fleet table updates to reflect the latest response

### Requirement: Per-crew detail fetched from Radar's per-crew endpoints

The SPA SHALL show a running crew's active tasks from its live agents request, `GET /api/crews/{crew_id}/agents`, and a stopped crew's active tasks from the crew's fleet-payload `agents` array, with no live request for a stopped crew. It SHALL render captain state from the `captain` field in the fleet payload. It SHALL NOT request scheduled jobs for any crew, and SHALL NOT request `/crews/{crew_id}/api/crons`. For stopped crews, it SHALL show registry task and captain state and explain that live schedule data is unavailable. Per-crew detail requests SHALL use Radar's same-origin `/api/crews/{crew_id}/` endpoints, which the portal routes to Radar.

#### Scenario: Expanding a crew row shows agent and captain state
- **WHEN** the operator expands a crew row in the Radar UI
- **THEN** the SPA renders a running crew's active tasks from `GET /api/crews/{crew_id}/agents`, or a stopped crew's active tasks from the fleet payload agents array
- **THEN** captain state (enabled/paused, schedule, current task) is rendered from the `captain` field in the fleet payload
- **THEN** no request is sent to `/crews/{crew_id}/api/crons` and no scheduled jobs are appended

#### Scenario: Stopped crew detail shows appropriate message
- **WHEN** the operator expands a stopped crew row
- **THEN** task and captain state from the registry are shown (no gateway probe)
- **THEN** a message indicates live schedule data is unavailable

### Requirement: Link to per-crew KC dashboard

When a crew entry in `/api/crews` includes a non-null `dashboard_url`, the
Radar SPA SHALL render a link that opens the per-crew KC dashboard in a new
browser tab.

#### Scenario: Crew with dashboard_url shows a link
- **WHEN** a crew's entry in `/api/crews` has a non-null `dashboard_url`
- **THEN** the Radar table row includes a link targeting that URL
- **THEN** clicking the link opens it in a new tab

#### Scenario: Crew without dashboard_url shows no link
- **WHEN** a crew's entry in `/api/crews` has `dashboard_url: null`
- **THEN** no dashboard link is rendered for that row

### Requirement: Fleet table shows crew busyness at a glance

The fleet table SHALL show an `N active` cyan badge and a purple `⚑ captain` or muted `⚑ paused` badge without row expansion. Stopped crews SHALL be dimmed and show `—` uptime; running status SHALL have a subtle green glow.

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

The Radar SPA HTML returned by `GET /` SHALL comply with the transport's
nonce-based Content Security Policy. The handler SHALL inject the per-request
`csp_nonce` (from `request.scope["csp_nonce"]`) into the `<style>` and `<script>`
nonce attributes. No inline `style=` attributes SHALL be used in JS-generated HTML;
all dynamic styling SHALL use CSS classes.

#### Scenario: No CSP violations on page load
- **WHEN** `GET /` is loaded in a browser with the transport's CSP headers active
- **THEN** no Content Security Policy violations are reported in the browser console

### Requirement: Ghostship brand theme

The Radar SPA SHALL use a visual theme consistent with the Ghostship brand:
deep space / cosmic nebula aesthetic with a dark background, CSS starfield, nebula
glow gradients, ghost emoji header, and per-role colour accents (teal for active
tasks, purple for captain/Raven, green glow for running status).

#### Scenario: Page loads with cosmic theme
- **WHEN** `GET /` is loaded
- **THEN** the page has a deep space dark background with subtle nebula glow
- **THEN** the header shows the 👻 ghost emoji with a pulsing purple/teal glow

### Requirement: Radar is read-only in this change

The Radar SPA SHALL NOT expose controls for launching, nuking, dispatching, or
steering crews in this version. All interactions are GET requests only.

#### Scenario: No write actions available
- **WHEN** the Radar page is loaded
- **THEN** no form submission, dispatch button, or destructive action control is present

# fleet-observability — Delta Specification (TRN-97)

> Delta spec: describes capabilities that do not yet exist. After
> implementation this spec is merged into the main openspec/specs tree.

## Capability: fleet-observability

A read-only browser-accessible dashboard (`ga-lighthouse`) that shows the
state of all Ghostship crews, their running tasks, per-persona mail activity,
and host resource pressure.

---

## Requirement: ga-lighthouse container

The Ghostship installation SHALL include a `ga-lighthouse` container when
`GA_LIGHTHOUSE_ENABLED=true` is set in the installation config. When the flag
is absent or `false`, no lighthouse service SHALL be present in `compose.yml`
and no Caddy route SHALL be present in `initial-config.json`.

### Scenario: lighthouse enabled at install

- **GIVEN** `GA_LIGHTHOUSE_ENABLED=true` is set before running `install.sh`
- **THEN** `DATA_DIR/compose.yml` SHALL contain a `ga-lighthouse` service block
- **AND** the `ga-lighthouse` service SHALL be attached to the `ga-portside`
  network only — `ga-starboard` MUST NOT appear in its `networks` list
- **AND** `DATA_DIR/caddy/initial-config.json` SHALL contain a route with
  `"@id": "ga-lighthouse"` matching `/lighthouse` and `/lighthouse/*`
- **AND** the route SHALL strip the `/lighthouse` prefix before forwarding
  to `ga-lighthouse:7474`

### Scenario: lighthouse disabled at install (default)

- **GIVEN** `GA_LIGHTHOUSE_ENABLED` is unset or `false`
- **THEN** `DATA_DIR/compose.yml` SHALL NOT contain any `ga-lighthouse` block
- **AND** `DATA_DIR/caddy/initial-config.json` SHALL NOT contain a
  `ga-lighthouse` route

---

## Requirement: fleet dashboard SPA

The `ga-lighthouse` container SHALL serve a single-page fleet dashboard at
its root path (`/`), accessible to browsers at `<portal-url>/lighthouse/`.

### Scenario: fleet view renders crew cards

- **WHEN** a browser navigates to `/lighthouse/`
- **THEN** the SPA SHALL display one card per crew in the fleet registry
- **AND** each card SHALL show: crew ID, status, count of running tasks,
  uptime, and a mail badge with total unread count
- **AND** the SPA SHALL refresh fleet data every 3 seconds via polling

### Scenario: empty fleet

- **WHEN** `GET /api/crews` returns an empty `crews` array
- **THEN** the SPA SHALL display an empty-state message indicating no crews
  are active

### Scenario: mail badge expansion

- **WHEN** a user clicks the mail badge on a crew card
- **THEN** the SPA SHALL fetch `GET /api/crews/{crew_id}/mail` and display
  per-persona unread counts and the subject of the most recent message per
  persona (or blank if the inbox is empty)
- **AND** the mail data SHALL be cached for 10 seconds before re-fetching

### Scenario: open crew dashboard link

- **WHEN** a user clicks "Open dashboard" on a crew card
- **THEN** the browser SHALL navigate to
  `<portal-origin>/crews/{crew_id}/ui/`
- **AND** lighthouse SHALL NOT proxy this navigation itself — it delegates
  to `ga-portal → ga-transport → crew gateway`

---

## Requirement: `GET /api/crews` transport endpoint

The `ga-transport` server SHALL expose a new REST endpoint
`GET /api/crews` that returns fleet registry state and live agent status.

### Scenario: returns crew list

- **WHEN** a client sends `GET /api/crews` with a valid Bearer token
  (or no token when `GA_API_KEY` is not set)
- **THEN** the server SHALL return `200 OK` with `application/json`
- **AND** the response body SHALL be a JSON object with:
  - a `"crews"` array where each element includes: `crew_id`, `container`,
    `status`, `composition`, `created_at`, `last_task_at`, `gateway_healthy`,
    `crew_image_version`, `uptime_secs`, `dashboard_url`, and
    `agents` (array of `{task_id, agent, done, elapsed_secs}`)
  - top-level `host_memory_available_gb`, `active_crews`, `max_active_crews`
    (matching the shape returned by the `crews()` MCP tool)

### Scenario: endpoint absent when flag off

- **WHEN** `GA_LIGHTHOUSE_ENABLED=false` (the default)
- **THEN** `GET /api/crews` SHALL return `404 Not Found`
- **AND** no route SHALL be registered for this path at transport startup

### Scenario: unauthenticated request rejected

- **WHEN** `GA_API_KEY` is set and a client sends `GET /api/crews` without a
  valid Bearer token
- **THEN** the server SHALL return `401 Unauthorized`
  with `WWW-Authenticate: Bearer`

---

## Requirement: `GET /api/crews/{crew_id}/mail` transport endpoint

The `ga-transport` server SHALL expose a new REST endpoint
`GET /api/crews/{crew_id}/mail` that returns per-persona mail summaries
for a given crew.

### Scenario: returns mail summary

- **WHEN** a client sends `GET /api/crews/{crew_id}/mail` and the crew
  exists and its container is running
- **THEN** the server SHALL return `200 OK` with `application/json`
- **AND** the response body SHALL be a JSON object with:
  - `"crew_id"`: the requested crew ID
  - `"mailboxes"`: an object keyed by persona name
    (`ghost`, `spectre`, `banshee`, `wraith`, `reaper`, `raven`,
    `captain`, `admiral`), each with:
    - `"unread"`: integer count of unread messages
    - `"subjects"`: array of subject strings (most recent first,
      maximum 5 subjects returned)

### Scenario: unknown crew

- **WHEN** a client sends `GET /api/crews/{crew_id}/mail` and `crew_id`
  is not in the registry
- **THEN** the server SHALL return `404 Not Found`

### Scenario: crew container not running

- **WHEN** the crew exists in the registry but its container is stopped
- **THEN** the server SHALL return `503 Service Unavailable` with a JSON
  error body describing the cause

### Scenario: endpoint absent when flag off

- **WHEN** `GA_LIGHTHOUSE_ENABLED=false` (the default)
- **THEN** `GET /api/crews/{crew_id}/mail` SHALL return `404 Not Found`

---

## Requirement: network isolation enforced

The `ga-lighthouse` container SHALL communicate with `ga-transport` over
`ga-portside` and SHALL have no network path to crew containers directly.

### Scenario: lighthouse cannot dial ga-starboard

- **WHEN** `ga-lighthouse` is running
- **THEN** it SHALL be able to resolve and connect to `ga-transport:64057`
  over `ga-portside`
- **AND** it SHALL NOT be able to resolve or connect to any `gs-{id}:5476`
  hostname (which are only on `ga-starboard`)

---

## Requirement: lighthouse authenticates to transport

The `ga-lighthouse` container SHALL include `X-Transport-Token` on all HTTP
requests it makes to `ga-transport`.

### Scenario: transport-token header present

- **WHEN** lighthouse makes any request to `ga-transport`
- **THEN** the request SHALL carry `X-Transport-Token: <secret>` where
  `<secret>` is the value from the mounted `ga-transport-secret` Podman
  secret file at `/run/secrets/ga-transport-secret`

### Scenario: missing secret causes startup failure

- **WHEN** the `ga-transport-secret` secret file is absent at container start
- **THEN** the lighthouse server SHALL log an error and refuse to serve any
  `GET /api/*` requests (returning `503 Service Unavailable`)
- **AND** it SHALL continue to serve the static SPA so the error is visible
  in the browser

---

## Requirement: portal session gate when GA_API_KEY is set

When `GA_API_KEY` is configured, the Caddy route for `/lighthouse/*` SHALL
enforce the same `gs_session` forward-auth check used for per-crew dashboards.

### Scenario: unauthenticated browser is redirected to login

- **WHEN** `GA_API_KEY` is set and a browser requests `/lighthouse/` without
  a valid `gs_session` cookie
- **THEN** Caddy SHALL return `302 Found` redirecting to `/dashboard/login`
  (same behaviour as per-crew dashboard ports)

### Scenario: authenticated browser reaches the SPA

- **WHEN** `GA_API_KEY` is set and a browser requests `/lighthouse/` with a
  valid `gs_session` cookie
- **THEN** Caddy SHALL forward the request to `ga-lighthouse:7474`
- **AND** the SPA SHALL be served

---

## Requirement: `GA_LIGHTHOUSE_ENABLED` config variable

The transport's `Config` dataclass SHALL include a `ga_lighthouse_enabled`
boolean field (default `false`) read from the `GA_LIGHTHOUSE_ENABLED`
environment variable using the existing `_env_bool_default_off` pattern.

### Scenario: env var absent

- **WHEN** `GA_LIGHTHOUSE_ENABLED` is not set
- **THEN** `Config.ga_lighthouse_enabled` SHALL be `false`

### Scenario: env var set to true

- **WHEN** `GA_LIGHTHOUSE_ENABLED=true` (or `1`, `yes`, `on`)
- **THEN** `Config.ga_lighthouse_enabled` SHALL be `true`
- **AND** the transport SHALL register `GET /api/crews` and
  `GET /api/crews/{crew_id}/mail` at startup

---

## Requirement: install.sh flag and documentation

`install.sh` SHALL accept `GA_LIGHTHOUSE_ENABLED` as a config-file variable
(same sourcing mechanism as all other config variables). `docs/configuration.md`
SHALL document this variable with its description, default (`false`), and an
example.

### Scenario: config file enables lighthouse

- **GIVEN** the user's `ghostship.conf` contains `GA_LIGHTHOUSE_ENABLED=true`
- **WHEN** `install.sh` is run with `--config ghostship.conf`
- **THEN** the lighthouse image SHALL be built, the compose block SHALL be
  generated, and the Caddy route SHALL be generated

### Scenario: documentation covers the variable

- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they SHALL find an entry for `GA_LIGHTHOUSE_ENABLED` with:
  - description of what lighthouse is
  - default value (`false`)
  - prerequisite note (the variable also needs to be set in the transport's
    environment via the compose block)

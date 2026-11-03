## MODIFIED Requirements

### Requirement: ga-radar serves the Radar SPA and fleet API

`ga-radar` SHALL expose five routes:

| Method | Path | Description |
|:-------|:-----|:------------|
| `GET /` | | Serve `static/index.html` |
| `GET /static/*` | | Serve static assets (CSS, JS) |
| `GET /api/crews` | | Proxy fleet data from `ga-transport /internal/crews` |
| `GET /api/crews/{crew_id}/agents` | | Proxy live task list for one crew from `ga-transport /internal/crews/{crew_id}/agents` |
| `GET /health` | | Return `{"status": "ok"}` — no auth required |

Static files in `radar/static/` (`index.html`, `style.css`, and the ES module
bundle: `main.js`, `format.js`, `state.js`, `render.js`, `data.js`) are baked
into the image at build time. `main.js` is the entry point; it polls
`GET /api/crews` every 5s with no external dependencies. On row expand, it
calls `GET /api/crews/{crew_id}/agents` to fetch live task data on demand.

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

## ADDED Requirements

### Requirement: ga-transport exposes per-crew agents endpoint

`ga-transport` SHALL expose `GET /internal/crews/{crew_id}/agents` (portside-internal, requires `X-Transport-Token`). It SHALL query the crew's KiroCrew gateway at `GET /api/tasks` with a 5-second timeout. It SHALL return `{"agents": [...]}` where each entry has `task_id`, `agent`, `done`, `elapsed_secs`. If the crew is not running or the gateway is unreachable, it SHALL return `{"agents": []}` with HTTP 200.

#### Scenario: Running crew returns live task list

- **WHEN** `GET /internal/crews/{crew_id}/agents` is requested for a running crew
- **THEN** transport queries the crew gateway at `GET /api/tasks`
- **THEN** the mapped task list is returned as `{"agents": [...]}`

#### Scenario: Stopped or unreachable crew returns empty agents

- **WHEN** `GET /internal/crews/{crew_id}/agents` is requested for a stopped crew or a crew whose gateway is unreachable
- **THEN** transport returns `{"agents": []}` with HTTP 200

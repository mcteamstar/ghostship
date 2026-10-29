## MODIFIED Requirements

### Requirement: Initial Caddy JSON configuration

`install.sh` SHALL write an `initial-config.json` under `DATA_DIR` that bootstraps
Caddy with a main HTTP server (default port 443) carrying: MCP routes (`/mcp*`),
file-transfer routes (`/files/*`), health (`/health`), the login/logout endpoints
(`/login`, `/login*`, `/logout`), the dashboard-auth endpoints (`/dashboard/auth`,
`/dashboard/login`), **a `ga-lighthouse` route that session-gates `/`,
`/api/crews*`, and `/crews/*/api/*` via `forward_auth` → `reverse_proxy`**. The
initial config SHALL contain no per-crew dashboard servers — those are added at
runtime. The config SHALL be loaded via
`caddy run --config /config/initial-config.json --resume`.

The `ga-lighthouse` route SHALL use the same `forward_auth` handler as the per-crew
dashboard port servers: it calls `GET /dashboard/auth` on the transport to validate
the `gs_session` cookie. On session validation success, Caddy proxies the request to
`ga-transport:64057`. When `GA_API_KEY` is unset, the `forward_auth` check SHALL be
omitted and requests proxy directly (matching the no-key passthrough behaviour
applied to `/mcp*`).

#### Scenario: Caddy starts with initial config
- **WHEN** the `ga-portal` container starts for the first time
- **THEN** the Caddy entrypoint loads `initial-config.json`
- **THEN** `GET /health` on the main port returns 200

#### Scenario: Lighthouse route enforces session via forward_auth
- **WHEN** `install.sh` generates `initial-config.json` with `GA_API_KEY` set
- **THEN** the `ga-lighthouse` route contains a `forward_auth` handler calling
  `/dashboard/auth` before `reverse_proxy`
- **THEN** `GET /` without a valid `gs_session` cookie returns a redirect to
  `/dashboard/login`

#### Scenario: Crews REST API is session-gated
- **WHEN** `install.sh` generates `initial-config.json` with `GA_API_KEY` set
- **THEN** the `ga-lighthouse` route's path matcher includes `/api/crews*`
- **THEN** `GET /api/crews` without a valid `gs_session` cookie returns a redirect
  to `/dashboard/login`

#### Scenario: Crew API proxy paths are session-gated
- **WHEN** `install.sh` generates `initial-config.json` with `GA_API_KEY` set
- **THEN** the `ga-lighthouse` route's path matcher includes `/crews/*/api/*`
- **THEN** `GET /crews/{id}/api/spawn` through the portal with a valid `gs_session`
  is forwarded to `ga-transport:64057`

#### Scenario: No-key install proxies lighthouse paths without session check
- **WHEN** `install.sh` generates `initial-config.json` with `GA_API_KEY` unset
- **THEN** the `ga-lighthouse` route proxies `/`, `/api/crews*`, `/crews/*/api/*`
  directly to `ga-transport:64057` without a `forward_auth` handler

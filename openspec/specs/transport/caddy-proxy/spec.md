# transport/caddy-proxy Specification

## Purpose

Manages a Caddy reverse-proxy container as a mandatory transport layer: generates its initial JSON config at install time, registers a per-crew Caddy server bound to the crew's dashboard port when a crew is launched, removes it when a crew is nuked, and enforces the MCP/file Bearer token at the edge — all without downtime or Caddy restarts.

## Requirements

### Requirement: `ga-portal` is always present

`ga-portal` SHALL always be included in the generated `compose.yml` and started by `install.sh`. There is no opt-out flag. The `GA_PORTAL_ENABLED` environment variable is removed and SHALL NOT be read or honoured. The service SHALL bind `GA_PORTAL_PORT` (default 64057) AND the dashboard port range (default 64058–64107) — Caddy owns those port bindings, not the transport. The Caddy admin API (port 2019) SHALL be bound to the internal `ga-portside` network only and SHALL NOT be published to the host. The `ga-transport` service SHALL NOT bind the dashboard port range. `ga-portal` SHALL be attached to `ga-portside` only and SHALL NOT be attached to `ga-starboard`.

#### Scenario: Install always starts ga-portal
- **WHEN** `install.sh` runs
- **THEN** `compose.yml` always contains a `ga-portal` service
- **THEN** `ga-portal` is started alongside `ga-transport`

#### Scenario: Fresh install includes Caddy config
- **WHEN** `install.sh` runs
- **THEN** `compose.yml` contains a `ga-portal` service with the `caddy:2` image, `GA_PORTAL_PORT` and the dashboard range bound, and no `2019:2019` host mapping
- **THEN** the `ga-transport` service does not bind the dashboard port range

### Requirement: Initial Caddy JSON configuration
`install.sh` SHALL write an `initial-config.json` under `DATA_DIR` that bootstraps Caddy with a main HTTP server (default port 443) carrying: MCP routes (`/mcp*`), file-transfer routes (`/files/*`), health (`/health`), and the dashboard-auth endpoints (`/dashboard-auth`, `/login-ui`, `/dashboard-login`). The initial config SHALL contain no per-crew dashboard servers — those are added at runtime. The config SHALL be loaded via `caddy run --config /config/initial-config.json --resume`.

#### Scenario: Caddy starts with initial config
- **WHEN** the `ga-portal` container starts for the first time
- **THEN** the Caddy entrypoint loads `initial-config.json`
- **THEN** `GET /health` on the main port returns 200

### Requirement: MCP and file routes enforce the Bearer token at the edge
When `GA_API_KEY` is set, the main-server `/mcp*` and `/files/*` routes SHALL require an `Authorization: Bearer <GA_API_KEY>` header. A request without the correct token SHALL be rejected by Caddy with 401 and `WWW-Authenticate: Bearer`, and SHALL NOT reach the transport process. The transport's own `BearerAuthMiddleware` SHALL remain active for defence in depth.

#### Scenario: MCP request with correct token is proxied
- **WHEN** a request to `/mcp` carries `Authorization: Bearer <GA_API_KEY>` and Caddy is enabled
- **THEN** Caddy proxies it to `ga-transport:64057`

#### Scenario: MCP request without token rejected at edge
- **WHEN** a request to `/mcp` carries no or an incorrect Bearer token and `GA_API_KEY` is set
- **THEN** Caddy returns 401 with `WWW-Authenticate: Bearer`
- **THEN** the request does not reach the transport process

### Requirement: Per-crew dashboard server registration
When a crew is successfully launched, the transport SHALL call the Caddy admin API to add an HTTP server bound to the crew's allocated dashboard port that reverse-proxies to `ga-transport:8000` with a URI rewrite to `/crews/{crew_id}/ui/{path}`, gated by a `forward_auth` handler (see the dashboard-auth capability). The server object SHALL carry `"@id": "crew-{crew_id}"` so it can be addressed directly for removal. `launch(dashboard=True)` SHALL allocate a port and register with `ga-portal` without checking a `GA_PORTAL_ENABLED` flag. The dashboard is always available on deployments where `ga-portal` is healthy.

#### Scenario: Crew launch registers Caddy dashboard server
- **WHEN** `launch(crew_id="alpha", dashboard=True)` completes successfully
- **THEN** `GET /config/id/crew-alpha` on the Caddy admin API returns a server object listening on the allocated port
- **THEN** the server's upstream is `ga-transport:8000` with a rewrite to `/crews/alpha/ui/{path}`
- **THEN** no per-port uvicorn listener thread is started in the transport

#### Scenario: Dashboard launch always succeeds when portal is healthy
- **WHEN** `launch(dashboard=True)` is called and `ga-portal` is running
- **THEN** a port is allocated, `_caddy_register_crew` is called, and `dashboard_url` is returned
- **WHEN** `ga-portal` is not running or Caddy registration fails
- **THEN** `launch` logs a warning but still returns `dashboard_url` (registration failure is non-fatal)

### Requirement: Per-crew dashboard server deregistration
When a crew is nuked, the transport SHALL call `DELETE /config/id/crew-{crew_id}` on the Caddy admin API to remove the corresponding server, and release the port back to the pool. Failure to contact the Caddy admin API SHALL be logged but SHALL NOT cause `nuke` to fail.

#### Scenario: Crew nuke removes Caddy server
- **WHEN** `nuke(crew_id="alpha", confirm=True)` is called and Caddy is enabled
- **THEN** `GET /config/id/crew-alpha` on the Caddy admin API returns 404 after nuke completes

#### Scenario: Caddy unreachable during nuke
- **WHEN** `nuke` is called and the Caddy admin API is unreachable
- **THEN** nuke completes and removes the crew from the registry
- **THEN** a warning is logged referencing the Caddy removal failure

### Requirement: Route re-registration on transport startup
On startup, the transport SHALL re-register a Caddy dashboard server for every crew in `crews.json` that has an allocated dashboard port. Re-registration SHALL be idempotent — an existing `@id` SHALL be handled gracefully.

#### Scenario: Restart re-registers dashboard servers
- **WHEN** the transport restarts with Caddy enabled and two crews in `crews.json` have dashboard ports
- **THEN** both `crew-{id}` servers exist on the Caddy admin API after `_reconcile_registry` runs

### Requirement: `X-Transport-Token` header injection

Caddy's JSON config SHALL add `header_up X-Transport-Token {env.GA_TRANSPORT_SECRET}` on every `reverse_proxy` directive targeting `ga-transport`. This applies to ALL upstream routes — MCP, files, dashboard, health — without exception. The header value is the `GA_TRANSPORT_SECRET` environment variable, which is mounted into `ga-portal` from the `ga-transport-secret` Podman secret at install time.

No Caddy route SHALL forward a request to `ga-transport` without this header. The transport middleware rejects any request that arrives without it.

#### Scenario: X-Transport-Token injection applies to every route

- **WHEN** `install.sh` writes the Caddy `initial-config.json`
- **THEN** every `reverse_proxy` handler targeting `ga-transport` includes `header_up X-Transport-Token {env.GA_TRANSPORT_SECRET}`
- **THEN** per-crew dashboard servers registered via `_caddy_register_crew` also include this header

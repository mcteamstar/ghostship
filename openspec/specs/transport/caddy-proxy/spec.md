# transport/caddy-proxy Specification

## Purpose

Manages a Caddy reverse-proxy container as a mandatory transport layer: generates its initial JSON config at install time, registers a per-crew Caddy server bound to the crew's dashboard port when a crew is launched, removes it when a crew is nuked, and enforces the MCP/file Bearer token at the edge — all without downtime or Caddy restarts.

## Requirements

### Requirement: `ga-portal` is always present

`install.sh` SHALL always include and start `ga-portal`; `GA_PORTAL_ENABLED` is removed and ignored. Caddy binds the portal and dashboard port ranges, while transport binds no dashboard ports. The Caddy admin API SHALL use a Unix-domain socket shared only with `ga-transport` and SHALL NOT be exposed on a TCP listener or published to the host. `ga-portal` uses only `ga-portside`, never `ga-starboard`.

#### Scenario: Install always starts ga-portal
- **WHEN** `install.sh` runs
- **THEN** `compose.yml` always contains a `ga-portal` service
- **THEN** `ga-portal` is started alongside `ga-transport`

#### Scenario: Fresh install includes Caddy config
- **WHEN** `install.sh` runs
- **THEN** `compose.yml` contains a `ga-portal` service with the `caddy:2` image, `GA_PORTAL_PORT` and the dashboard range bound, and no `2019:2019` host mapping
- **THEN** the `ga-transport` service does not bind the dashboard port range
- **THEN** `ga-portal` and `ga-transport` share the Caddy admin socket directory
- **THEN** no other service mounts the Caddy admin socket directory

### Requirement: Initial Caddy JSON configuration

`install.sh` SHALL write `DATA_DIR/initial-config.json` and run Caddy with it using `--resume`. The default HTTP server routes MCP, files, health, login/logout, dashboard auth, and Radar. Radar `/`, `/api/crews*`, and `/crews/*/api/*` use `forward_auth` to validate `gs_session` before proxying to transport; omit auth when `GA_API_KEY` is unset. Per-crew servers are added at runtime.

#### Scenario: Caddy starts with initial config
- **WHEN** the `ga-portal` container starts for the first time
- **THEN** the Caddy entrypoint loads `initial-config.json`
- **THEN** `GET /health` on the main port returns 200

#### Scenario: Lighthouse route enforces session via forward_auth
- **WHEN** `install.sh` generates `initial-config.json` with `GA_API_KEY` set
- **THEN** the `ga-radar` route contains a `forward_auth` handler calling
  `/dashboard/auth` before `reverse_proxy`
- **THEN** `GET /` without a valid `gs_session` cookie returns a redirect to
  `/dashboard/login`

#### Scenario: Crews REST API is session-gated
- **WHEN** `install.sh` generates `initial-config.json` with `GA_API_KEY` set
- **THEN** the `ga-radar` route's path matcher includes `/api/crews*`
- **THEN** `GET /api/crews` without a valid `gs_session` cookie returns a redirect
  to `/dashboard/login`

#### Scenario: Crew API proxy paths are session-gated
- **WHEN** `install.sh` generates `initial-config.json` with `GA_API_KEY` set
- **THEN** the `ga-radar` route's path matcher includes `/crews/*/api/*`
- **THEN** `GET /crews/{id}/api/spawn` through the portal with a valid `gs_session`
  is forwarded to `ga-transport:64057`

#### Scenario: No-key install proxies lighthouse paths without session check
- **WHEN** `install.sh` generates `initial-config.json` with `GA_API_KEY` unset
- **THEN** the `ga-radar` route proxies `/`, `/api/crews*`, `/crews/*/api/*`
  directly to `ga-transport:64057` without a `forward_auth` handler

### Requirement: MCP routes enforce Bearer auth and file routes enforce signed capabilities
When `GA_API_KEY` is set, the main-server `/mcp*` routes SHALL require an `Authorization: Bearer <GA_API_KEY>` header. Caddy SHALL reject missing or incorrect bearer credentials with 401 and `WWW-Authenticate: Bearer` before the request reaches the transport. A valid presigned `/files/*` URL SHALL be authenticated by its HMAC signature and expiry and SHALL NOT require the API key; unsigned file requests SHALL use the bearer-protected route. The transport's bearer and HMAC checks SHALL remain active for defence in depth.

#### Scenario: MCP request with correct token is proxied
- **WHEN** a request to `/mcp` carries `Authorization: Bearer <GA_API_KEY>` and Caddy is enabled
- **THEN** Caddy proxies it to `ga-transport:64057`

#### Scenario: MCP request without token rejected at edge
- **WHEN** a request to `/mcp` carries no or an incorrect Bearer token and `GA_API_KEY` is set
- **THEN** Caddy returns 401 with `WWW-Authenticate: Bearer`
- **THEN** the request does not reach the transport process

#### Scenario: Valid presigned file URL does not require the API key
- **WHEN** a request to `/files/*` carries a valid `sig` and `expires` query and `GA_API_KEY` is set
- **THEN** Caddy proxies the request without requiring a bearer header and the transport validates the HMAC capability

#### Scenario: Unsigned file request uses bearer protection
- **WHEN** a request to `/files/*` has no `sig` query and `GA_API_KEY` is set
- **THEN** Caddy requires the bearer token before proxying the request

#### Scenario: Invalid signed file URL is rejected by transport
- **WHEN** a request to `/files/*` carries an invalid or expired signature
- **THEN** the transport rejects the request with 403 even if the API key is unset

### Requirement: Per-crew dashboard server registration
After a successful launch with `dashboard=True`, transport SHALL register a Caddy server on the allocated port, identified as `crew-{crew_id}`, with `forward_auth` and a proxy to `ga-transport:64057` rewriting to `/crews/{crew_id}/ui/{path}`. Dashboard registration is unconditional when the portal is healthy.

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

Every Caddy reverse proxy to `ga-transport` SHALL inject `X-Transport-Token` from `GA_TRANSPORT_SECRET`, sourced from the Podman secret. No route may omit the header; transport rejects requests without it.

#### Scenario: X-Transport-Token injection applies to every route

- **WHEN** `install.sh` writes the Caddy `initial-config.json`
- **THEN** every `reverse_proxy` handler targeting `ga-transport` includes `header_up X-Transport-Token {env.GA_TRANSPORT_SECRET}`
- **THEN** per-crew dashboard servers registered via `_caddy_register_crew` also include this header

### Requirement: WebSocket upgrades bypass forward_auth on the dashboard port
Each per-crew Caddy server SHALL order a `Connection: Upgrade` route before its HTTP catch-all. WebSockets proxy directly without `forward_auth`; transport SHALL validate `gs_session` before upgrade and return HTTP 401 when invalid. HTTP retains `forward_auth` when enabled, or proxies directly without an API key. Both routes inject `X-Transport-Token`, dial `ga-transport:{PORT}`, and rewrite to `/crews/{crew_id}/ui/{path}`.

#### Scenario: SPA WebSocket connection bypasses forward_auth and is upgraded
- **WHEN** the KiroCrew SPA opens a WebSocket connection (`Connection: Upgrade`)
  through a crew's dashboard port with a valid `gs_session` cookie
- **THEN** the Caddy server object has a route matching
  `{"header": {"Connection": ["Upgrade"]}}` that does not contain the
  `forward_auth` handler and proxies directly to the transport UI proxy
- **THEN** the transport validates the `gs_session` cookie and completes the
  WebSocket upgrade (HTTP 101 Switching Protocols)

#### Scenario: WebSocket upgrade without a valid session is refused
- **WHEN** a WebSocket connection arrives on a crew dashboard path without a
  valid `gs_session` cookie
- **THEN** the transport rejects the upgrade with HTTP 401 and no WebSocket
  connection is established

#### Scenario: Valid session allows WebSocket upgrade
- **WHEN** a WebSocket connection arrives on `/crews/{crew_id}/ui/...` with a
  valid and unexpired `gs_session` cookie
- **THEN** `SessionStore.validate()` returns the session successfully and the
  connection is proxied to the crew gateway as a WebSocket

### Requirement: Caddy admin API is accessible only to Transport
The Caddy admin API SHALL listen on a Unix-domain socket in a directory shared by `ga-portal` and `ga-transport`. Filesystem permissions on the socket SHALL allow the Transport process to connect. The admin API SHALL NOT listen on a TCP address. `ga-radar` and crew containers SHALL NOT receive a mount of the socket directory. Caddy origin or host checks SHALL NOT be treated as authentication for admin API callers.

#### Scenario: Transport manages dashboard routes through the socket
- **WHEN** Transport registers, removes, or reconciles a crew dashboard route
- **THEN** its admin API request reaches Caddy through the shared Unix-domain socket and Caddy applies the change

#### Scenario: Radar cannot reach the Caddy admin API
- **WHEN** Radar attempts to connect to the Caddy admin API
- **THEN** it has no mounted socket and no TCP admin listener is available to it
- **THEN** the request cannot change Caddy configuration

#### Scenario: Public Caddy listeners remain available
- **WHEN** the admin API is moved to a Unix-domain socket
- **THEN** the portal listener and per-crew dashboard listeners remain available on their configured host ports

#### Scenario: Admin API is not published to the host
- **WHEN** the generated Compose configuration is inspected
- **THEN** no host port mapping exposes the Caddy admin API

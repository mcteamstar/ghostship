# transport/dashboard-proxy Specification

## Purpose

Defines the port-based routing model for crew dashboard UIs: each crew launched with `dashboard=True` gets a dedicated port, serving its UI via either the transport's per-port uvicorn proxies (Caddy disabled) or Caddy's TLS-terminated, auth-gated listeners (Caddy enabled). There is exactly one routing mode at a time; enabling Caddy is a clean cutover.

## Requirements

### Requirement: Dashboard routing mode
Dashboard routing SHALL remain port-based in all cases — each crew UI is served at a dedicated port from the `GA_DASHBOARD_PORT_RANGE` (default 64058–64107), because the KiroCrew SPA requires a root origin. Path-prefix routing (`/crews/{id}/ui/`) and subdomain routing SHALL NOT be used. When `GA_PORTAL_ENABLED=true`, Caddy SHALL bind those per-crew ports (adding TLS and `forward_auth` on each) and proxy to `http://gs-{id}:5476/`, and the transport SHALL NOT start its per-port uvicorn listener threads. When `GA_PORTAL_ENABLED=false`, the transport SHALL bind and serve those ports itself, exactly as before this change. There is no mode in which both bind the same port simultaneously — enabling Caddy is a clean cutover.

#### Scenario: Caddy-mode dashboard access
- **WHEN** `GA_PORTAL_ENABLED=true` and crew `alpha` is launched with `dashboard=True`
- **THEN** the crew dashboard is accessible over HTTPS at the crew's dedicated port (e.g. `https://<host>:64058/`)
- **THEN** Caddy binds that port and the transport starts no per-port listener for the crew
- **THEN** `launch` returns a `dashboard_url` of the form `https://<host>:<port>/`

#### Scenario: Per-port transport mode when Caddy disabled
- **WHEN** `GA_PORTAL_ENABLED=false` and `GA_DASHBOARD_PORT_ENABLED=true`
- **THEN** the transport binds the port and runs its per-port uvicorn proxy exactly as before TRN-92
- **THEN** `launch(dashboard=True)` allocates a port and starts a daemon-thread proxy

#### Scenario: dashboard_url shape reflects the active terminator
- **WHEN** `GA_PORTAL_ENABLED=true` and crew `alpha` has port 64058 allocated
- **THEN** `crews()` returns `dashboard_url: "https://<host>:64058/"` for `alpha`
- **WHEN** `GA_PORTAL_ENABLED=false` and crew `beta` has port 64059 allocated
- **THEN** `crews()` returns `dashboard_url: "http://localhost:64059/"` for `beta`

### Requirement: Per-crew dashboard routing when Portal enabled

When `GA_PORTAL_ENABLED=true`, `ga-portal` (Caddy) SHALL route each crew's dashboard port traffic to the transport's cookie-injecting proxy endpoint (`/crews/{crew_id}/ui/`) rather than directly to the crew gateway (`gs-{crew_id}:5476`). The transport proxy endpoint SHALL inject the crew's `mc_token_5476` session cookie on every forwarded request and SHALL handle both HTTP and WebSocket connections.

The crew gateway (`gs-{crew_id}:5476`) SHALL be reached exclusively from the transport, ensuring the session cookie's IP binding is satisfied.

#### Scenario: Dashboard request via Portal is authenticated
- **WHEN** `GA_PORTAL_ENABLED=true` and a browser requests a crew dashboard port (e.g. `http://host:64058/`)
- **THEN** `ga-portal` proxies to `ga-transport:{PORT}/crews/{crew_id}/ui/`
- **THEN** the transport injects `Cookie: mc_token_5476=<crew_token>` on the forwarded request to `gs-{crew_id}:5476`
- **THEN** the KiroCrew SPA loads authenticated without a "Session expired" prompt

#### Scenario: WebSocket connections are proxied correctly
- **WHEN** the KiroCrew SPA opens a WebSocket connection through the dashboard port
- **THEN** the transport proxy endpoint upgrades the connection and bidirectionally relays frames between the browser and `gs-{crew_id}:5476`

#### Scenario: Token expiry is handled transparently
- **WHEN** the stored `mc_token_5476` for a crew is near expiry (> 80% of `KC_GATEWAY_TOKEN_TTL` elapsed)
- **THEN** the transport proxy endpoint re-mints the cookie before forwarding the request
- **THEN** the browser experiences no interruption

### Requirement: Caddy crew server routes to transport proxy

When registering a per-crew Caddy server via `_caddy_register_crew`, the transport SHALL configure the Caddy `reverse_proxy` to dial `ga-transport:{PORT}` and SHALL include a `rewrite` that maps the incoming request path to `/crews/{crew_id}/ui/{original_path}` before forwarding. The transport SHALL NOT inject the session cookie in the Caddy server config.

#### Scenario: Crew Caddy server upstreams the transport with a UI rewrite
- **WHEN** `_caddy_register_crew` registers a per-crew dashboard server
- **THEN** the crew `reverse_proxy` handler's upstream dial is `ga-transport:{PORT}`, not `gs-{crew_id}:5476`
- **THEN** the handler includes a `rewrite` mapping the incoming path to `/crews/{crew_id}/ui/{original_path}`
- **THEN** the handler injects no `Cookie` header — cookie injection is owned by the transport's UI-proxy endpoint

### Requirement: `ga-portal` is not on `ga-net`

`ga-portal` SHALL NOT be attached to the `ga-net` Podman network. All Caddy upstream targets SHALL be `ga-transport:{PORT}` only — Caddy SHALL have no network path to crew containers (`gs-*`). `ga-net` is reserved for transport ↔ crew container communication.

#### Scenario: Caddy has no network path to crew containers
- **WHEN** the compose stack is generated with `GA_PORTAL_ENABLED=true`
- **THEN** the `ga-portal` service is not attached to `ga-net`
- **THEN** `ga-portal` reaches `ga-transport:{PORT}` over the compose default network
- **THEN** `ga-portal` has no route to any `gs-*` crew container

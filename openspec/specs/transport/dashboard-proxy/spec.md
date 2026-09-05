# transport/dashboard-proxy Specification

## Purpose

Defines the port-based routing model for crew dashboard UIs: each crew launched with `dashboard=True` gets a dedicated port. `ga-portal` (Caddy) is always present (TRN-103) and binds those ports, routing traffic through the transport's cookie-injecting proxy endpoint to the crew gateway. Dashboard access is unconditional — `launch(dashboard=True)` SHALL NOT be gated on any `GA_PORTAL_ENABLED` flag.

## Requirements

### Requirement: Dashboard routing mode

Dashboard routing SHALL remain port-based — each crew UI is served at a dedicated port from the `GA_DASHBOARD_PORT_RANGE` (default 64058–64107), because the KiroCrew SPA requires a root origin. Path-prefix routing and subdomain routing SHALL NOT be used. `ga-portal` (Caddy) is always present (TRN-103); dashboard access SHALL NOT be gated on any `GA_PORTAL_ENABLED` flag. `launch(dashboard=True)` SHALL allocate a port and register the crew with Portal whenever Portal is healthy.

#### Scenario: Dashboard access is unconditional

- **WHEN** `launch(dashboard=True)` is called and `ga-portal` is running
- **THEN** a port is allocated from `GA_DASHBOARD_PORT_RANGE`, the crew is registered with Portal, and a `dashboard_url` is returned
- **THEN** no `GA_PORTAL_ENABLED` flag is read or honoured

#### Scenario: Dashboard requires Portal

- **WHEN** `launch(dashboard=True)` is called and `ga-portal` is healthy
- **THEN** a port is allocated and the crew is registered with Portal; there is no `GA_PORTAL_ENABLED=false` branch and no error is returned on that basis
- **THEN** if Caddy registration itself fails, `launch` logs a warning but still returns `dashboard_url` (registration failure is non-fatal)

#### Scenario: Caddy-mode dashboard access

- **WHEN** crew `alpha` is launched with `dashboard=True`
- **THEN** the crew dashboard is accessible at the crew's dedicated port (e.g. `http://<host>:64058/`)
- **THEN** Caddy binds that port and routes to `ga-transport:{PORT}/crews/alpha/ui/`
- **THEN** `launch` returns a `dashboard_url` of the form `<scheme>://<host>:<port>/`

#### Scenario: dashboard_url shape reflects TLS mode

- **WHEN** `GA_PORTAL_TLS_MODE=off`
- **THEN** `dashboard_url` uses `http://`
- **WHEN** `GA_PORTAL_TLS_MODE` is `internal`, `tailscale`, or `acme`
- **THEN** `dashboard_url` uses `https://`

### Requirement: Per-crew dashboard routing when Portal enabled

`ga-portal` (Caddy) SHALL route each crew's dashboard port traffic to the transport's cookie-injecting proxy endpoint (`/crews/{crew_id}/ui/`) rather than directly to the crew gateway (`gs-{crew_id}:5476`). The transport proxy endpoint SHALL inject the crew's `mc_token_5476` session cookie on every forwarded request and SHALL handle both HTTP and WebSocket connections.

The crew gateway (`gs-{crew_id}:5476`) SHALL be reached exclusively from the transport. This satisfies the KiroCrew gateway's IP-binding constraint — the cookie is bound to the IP that performed the token exchange, which is `ga-transport`'s IP on `ga-net`.

#### Scenario: Dashboard request via Portal is authenticated

- **WHEN** a browser requests a crew dashboard port (e.g. `http://host:64058/`)
- **THEN** `ga-portal` proxies to `ga-transport:{PORT}/crews/{crew_id}/ui/`
- **THEN** the transport injects `Cookie: mc_token_5476=<crew_token>` on the forwarded request to `gs-{crew_id}:5476`
- **THEN** the KiroCrew SPA loads authenticated without a "Session expired" prompt

#### Scenario: WebSocket connections are proxied correctly

- **WHEN** the KiroCrew SPA opens a WebSocket connection through the dashboard port
- **THEN** the transport proxy endpoint upgrades the connection and bidirectionally relays frames between the browser and `gs-{crew_id}:5476`
- **THEN** the upstream WebSocket handshake carries both `Cookie: mc_token_5476=<crew_token>` and `Origin: http://gs-{crew_id}:{CREW_GATEWAY_PORT}` — the gateway validates both

#### Scenario: Token expiry is handled transparently

- **WHEN** the stored `mc_token_5476` cookie's `session_exp` JWT claim is within 20% of `KC_GATEWAY_TOKEN_TTL` (default 24h) of expiring
- **THEN** the transport proxy endpoint re-mints the cookie before forwarding the request
- **THEN** the browser experiences no interruption
- **NOTE**: KiroCrew tokens are 2-part JWTs (`payload.signature`, not `header.payload.signature`). The `session_exp` claim (24h session lifetime) governs refresh; the `exp` claim is a short-lived one-time-URL TTL (~5 min) and SHALL NOT be used for the near-expiry check.

#### Scenario: Gateway 403 triggers cookie refresh

- **WHEN** the crew gateway returns 403 on a proxied request (e.g. after a container restart invalidates the stored cookie)
- **THEN** the transport re-mints the cookie and retries the request

### Requirement: Caddy crew server routes to transport proxy

When registering a per-crew Caddy server via `_caddy_register_crew`, the transport SHALL configure the Caddy `reverse_proxy` to dial `ga-transport:{PORT}` and SHALL include a `rewrite` that maps the incoming request path to `/crews/{crew_id}/ui/{original_path}` before forwarding. The transport SHALL NOT inject the session cookie in the Caddy server config.

#### Scenario: Crew Caddy server upstreams the transport with a UI rewrite

- **WHEN** `_caddy_register_crew` registers a per-crew dashboard server
- **THEN** the crew `reverse_proxy` handler's upstream dial is `ga-transport:{PORT}`, not `gs-{crew_id}:5476`
- **THEN** the handler includes a `rewrite` mapping the incoming path to `/crews/{crew_id}/ui/{original_path}`
- **THEN** the handler injects no `Cookie` header — cookie injection is owned by the transport's UI-proxy endpoint

### Requirement: `ga-portal` network topology

`ga-portal` SHALL be on `ga-portside` only; `gs-*` crew containers SHALL be on `ga-starboard` only. The requirement that `ga-portal` and `ga-transport` share `ga-net` is superseded. The invariant that `ga-portal` SHALL NOT make direct connections to crew containers (`gs-*`) continues to hold and is now additionally enforced at the network layer: crew container hostnames are not resolvable from `ga-portside`.

The routing path — browser → `ga-portal` → `ga-transport:/crews/{id}/ui/` → `gs-<crew_id>:5476` — continues to work because `ga-transport` bridges both networks: it is reachable by `ga-portal` over `ga-portside`, and can reach `gs-*` containers over `ga-starboard`.

#### Scenario: ga-portal and ga-transport share ga-portside

- **WHEN** `install.sh` generates `compose.yml`
- **THEN** both `ga-portal` and `ga-transport` services declare `ga-portside` in their `networks:` block
- **THEN** `ga-portal` does NOT declare `ga-starboard`
- **THEN** no Caddy upstream in the initial config or in any `_caddy_register_crew` call dials a `gs-*` address directly — all upstreams target `ga-transport`

#### Scenario: Dashboard request still reaches crew gateway

- **WHEN** a browser requests a crew dashboard port (e.g. `https://host:64058/`)
- **THEN** `ga-portal` proxies to `ga-transport:{PORT}/crews/{crew_id}/ui/` over `ga-portside`
- **THEN** `ga-transport` proxies to `gs-{crew_id}:5476` over `ga-starboard`
- **THEN** the KiroCrew SPA loads authenticated

#### Scenario: Crew containers not reachable directly from ga-portal

- **WHEN** `ga-portal` has a misconfigured upstream targeting `gs-<crew_id>:5476`
- **THEN** the connection fails — `gs-*` are not on `ga-portside`

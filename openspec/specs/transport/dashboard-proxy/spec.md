# transport/dashboard-proxy Specification

## Purpose

Defines the port-based routing model for crew dashboard UIs: each crew launched with `dashboard=True` gets a dedicated port. When `GA_PORTAL_ENABLED=true`, `ga-portal` (Caddy) binds those ports and routes traffic through the transport's cookie-injecting proxy endpoint to the crew gateway. When `GA_PORTAL_ENABLED=false`, dashboard access is unavailable (`launch(dashboard=True)` returns an error).

## Requirements

### Requirement: Dashboard routing mode

Dashboard routing SHALL remain port-based — each crew UI is served at a dedicated port from the `GA_DASHBOARD_PORT_RANGE` (default 64058–64107), because the KiroCrew SPA requires a root origin. Path-prefix routing and subdomain routing SHALL NOT be used. `GA_PORTAL_ENABLED=true` is **required** for dashboard access; `launch(dashboard=True)` with Portal disabled SHALL return an error.

#### Scenario: Dashboard requires Portal

- **WHEN** `GA_PORTAL_ENABLED=false` and `launch(dashboard=True)` is called
- **THEN** the call returns an error: `"dashboard access requires GA_PORTAL_ENABLED=true; re-run install.sh and re-launch any existing dashboard crews — see docs/dashboard-proxy.md"`
- **THEN** no port is allocated and `dashboard_url` is not set

#### Scenario: Caddy-mode dashboard access

- **WHEN** `GA_PORTAL_ENABLED=true` and crew `alpha` is launched with `dashboard=True`
- **THEN** the crew dashboard is accessible at the crew's dedicated port (e.g. `http://<host>:64058/`)
- **THEN** Caddy binds that port and routes to `ga-transport:{PORT}/crews/alpha/ui/`
- **THEN** `launch` returns a `dashboard_url` of the form `<scheme>://<host>:<port>/`

#### Scenario: dashboard_url shape reflects TLS mode

- **WHEN** `GA_PORTAL_ENABLED=true` and `GA_PORTAL_TLS_MODE=off`
- **THEN** `dashboard_url` uses `http://`
- **WHEN** `GA_PORTAL_ENABLED=true` and `GA_PORTAL_TLS_MODE` is `internal`, `tailscale`, or `acme`
- **THEN** `dashboard_url` uses `https://`

### Requirement: Per-crew dashboard routing when Portal enabled

When `GA_PORTAL_ENABLED=true`, `ga-portal` (Caddy) SHALL route each crew's dashboard port traffic to the transport's cookie-injecting proxy endpoint (`/crews/{crew_id}/ui/`) rather than directly to the crew gateway (`gs-{crew_id}:5476`). The transport proxy endpoint SHALL inject the crew's `mc_token_5476` session cookie on every forwarded request and SHALL handle both HTTP and WebSocket connections.

The crew gateway (`gs-{crew_id}:5476`) SHALL be reached exclusively from the transport. This satisfies the KiroCrew gateway's IP-binding constraint — the cookie is bound to the IP that performed the token exchange, which is `ga-transport`'s IP on `ga-net`.

#### Scenario: Dashboard request via Portal is authenticated

- **WHEN** `GA_PORTAL_ENABLED=true` and a browser requests a crew dashboard port (e.g. `http://host:64058/`)
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

`ga-portal` and `ga-transport` SHALL both be attached to `ga-net` so Caddy can dial `ga-transport:{PORT}`. podman-compose has no implicit default network (unlike Docker Compose), so any two containers that need to communicate must share a named network. `ga-portal` SHALL NOT be configured to make direct connections to crew containers (`gs-*`) — all crew traffic routes via the transport proxy endpoint. The `ga-net` membership does not itself prevent `ga-portal` from reaching crew containers; the constraint is enforced by Caddy's config (all upstreams point to `ga-transport` only).

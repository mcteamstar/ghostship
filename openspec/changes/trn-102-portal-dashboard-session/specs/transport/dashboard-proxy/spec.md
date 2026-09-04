## MODIFIED Requirements

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

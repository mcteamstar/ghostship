# Spec Delta

## MODIFIED Requirements

### Requirement: Per-crew dashboard routing when Portal enabled

`ga-portal` (Caddy) SHALL route each crew's dashboard port traffic to the transport's cookie-injecting proxy endpoint (`/crews/{crew_id}/ui/`) rather than directly to the crew gateway (`gs-{crew_id}:5476`). The transport proxy endpoint SHALL inject the crew's `mc_token_5476` session cookie on every forwarded request and SHALL handle both HTTP and WebSocket connections.

The crew gateway (`gs-{crew_id}:5476`) SHALL be reached exclusively from the transport. This satisfies the KiroCrew gateway's IP-binding constraint — the cookie is bound to the IP that performed the token exchange, which is `ga-transport`'s IP on `ga-starboard`.

#### Scenario: Dashboard request via Portal is authenticated

- **WHEN** a browser requests a crew dashboard port (e.g. `http://host:64058/`)
- **THEN** `ga-portal` proxies to `ga-transport:{PORT}/crews/{crew_id}/ui/`
- **THEN** the transport injects `Cookie: mc_token_5476=<crew_token>` on the forwarded request to `gs-{crew_id}:5476`
- **THEN** the KiroCrew SPA loads authenticated without a "Session expired" prompt

#### Scenario: WebSocket connections are proxied correctly

- **WHEN** the KiroCrew SPA opens a WebSocket connection through the dashboard port
- **THEN** the transport validates the client dashboard session and browser origin when dashboard authentication is enabled before opening the upstream connection
- **THEN** the transport proxy endpoint upgrades the connection and bidirectionally relays frames between the browser and `gs-{crew_id}:5476`
- **THEN** the upstream WebSocket handshake carries `Cookie: mc_token_5476=<crew_token>` and `Origin: http://localhost:{CREW_GATEWAY_PORT}` — the loopback origin is always in the gateway's `allowed_origins` set regardless of config
- **THEN** the gateway responds `101 Switching Protocols`

#### Scenario: Token expiry is handled transparently

- **WHEN** the stored `mc_token_5476` cookie's `session_exp` JWT claim is within 20% of `KC_GATEWAY_TOKEN_TTL` (default 24h) of expiring
- **THEN** the transport proxy endpoint re-mints the cookie before forwarding the request
- **THEN** the browser experiences no interruption
- **NOTE**: KiroCrew tokens are 2-part JWTs (`payload.signature`, not `header.payload.signature`). The `session_exp` claim (24h session lifetime) governs refresh; the `exp` claim is a short-lived one-time-URL TTL (~5 min) and SHALL NOT be used for the near-expiry check.

#### Scenario: Gateway 403 triggers cookie refresh

- **WHEN** the crew gateway returns 403 on a proxied request (e.g. after a container restart invalidates the stored cookie)
- **THEN** the transport re-mints the cookie and retries the request

#### Scenario: Dashboard live features unlock over the connected socket

- **WHEN** the KiroCrew SPA's WebSocket connects successfully (101) through the dashboard port
- **THEN** the sessions list loads, live task updates stream, and the import modal can be dismissed normally — the behaviours previously blocked by the 403

## REMOVED Requirements

### Requirement: Gateway allowed-origins includes the crew's own hostname

**Reason**: The current transport does not patch `config.local.json` to set `dashboard.url` or send the crew hostname as the upstream WebSocket Origin. It sends `http://localhost:{CREW_GATEWAY_PORT}`, which KiroCrew allows by default. The hostname-specific config and handshake scenarios were stale and contradicted the runtime; the general dashboard-live-features scenario remains under per-crew dashboard routing.

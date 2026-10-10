# transport/dashboard-proxy

## MODIFIED Requirements

### Requirement: WebSocket connections are proxied correctly

The transport WS proxy SHALL send `Origin: http://localhost:{CREW_GATEWAY_PORT}`
on the upstream WebSocket handshake. This loopback origin is always present in
the KiroCrew gateway's `allowed_origins` set regardless of config. The
`BearerAuthMiddleware` SHALL dispatch WS upgrades for `/crews/*/ui` paths using
the handler registered in `public_routes` — these paths are gated by Caddy's
`gs_session` forward-auth, not bearer tokens.

#### Scenario: WebSocket connections are proxied correctly

- **WHEN** the KiroCrew SPA opens a WebSocket connection through the dashboard port
- **THEN** `BearerAuthMiddleware` dispatches the WS upgrade to the handler
  registered in `public_routes` (no bearer check)
- **THEN** the transport proxy endpoint upgrades the connection and
  bidirectionally relays frames between the browser and `gs-{crew_id}:5476`
- **THEN** the upstream WebSocket handshake carries
  `Cookie: mc_token_5476=<crew_token>` and
  `Origin: http://localhost:{CREW_GATEWAY_PORT}`
- **THEN** the gateway responds `101 Switching Protocols`

#### Scenario: WS upgrade is dispatched without bearer check

- **WHEN** a WebSocket upgrade arrives at `/crews/{crew_id}/ui/api/ws`
- **THEN** `BearerAuthMiddleware` dispatches it to the handler registered in
  `public_routes` (no bearer token required)
- **THEN** the upstream connection is established and the browser WebSocket
  connects successfully

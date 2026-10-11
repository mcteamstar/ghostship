## ADDED Requirements

### Requirement: WebSocket upgrade authenticated by gs_session cookie, not app token
The transport WS proxy route (the `Connection: Upgrade` route in
`CaddyPortal.register_crew`) SHALL authenticate WebSocket upgrade requests
solely via the `gs_session` session cookie inherited from the dashboard SPA's
initial HTTP load. The WS proxy route SHALL NOT set or forward an `X-App-Token`
header (or any per-app token) to the upstream crew gateway. The WS route
bypasses `forward_auth` because the browser context already carries a validated
`gs_session` from the SPA load; this invariant MUST be preserved across gateway
version upgrades.

#### Scenario: WS upgrade proxy carries no app token
- **WHEN** a browser with a valid `gs_session` cookie opens a WebSocket connection to the crew dashboard
- **THEN** the transport proxies the upgrade to the upstream crew gateway with the `X-Transport-Token` header set and no `X-App-Token` header present

#### Scenario: Cookie-authenticated WS connection receives the full crew event stream
- **WHEN** a logged-in operator's dashboard WS connection is established (authenticated via `gs_session`, carrying no app token)
- **THEN** the upstream crew gateway delivers the full crew session event stream (turn started, turn ended, new message) without per-app filtering

#### Scenario: Per-app WS scoping does not apply to cookie-authenticated connections
- **WHEN** the upstream KiroCrew gateway has per-app WS event scoping enabled (filtering connections that present an `X-App-Token`)
- **THEN** a cookie-authenticated dashboard WS connection is not subject to that filter and continues to receive all crew events

## MODIFIED Requirements

### Requirement: WebSocket upgrades bypass forward_auth on the dashboard port
The per-crew Caddy dashboard server registered via `_caddy_register_crew` SHALL
expose two routes: a WebSocket-upgrade route and an HTTP catch-all route, in that
order. The WebSocket route SHALL be matched by the `Connection: Upgrade` request
header and SHALL proxy directly to the transport UI proxy WITHOUT the `forward_auth`
handler, so the upgrade handshake is preserved. The HTTP catch-all route (no matcher)
SHALL retain the existing `forward_auth`-then-`reverse_proxy` behaviour (or
`reverse_proxy` only when no API key is configured). Both routes SHALL inject the
`X-Transport-Token` header and dial `ga-transport:{PORT}` with the
`/crews/{crew_id}/ui/{path}` rewrite. Ordering the WebSocket route first guarantees
upgrade requests never fall through to the `forward_auth` path.

The transport SHALL additionally enforce session validation on WebSocket upgrade
requests that arrive on a crew dashboard port path prefix. Before completing a
WebSocket upgrade to `/crews/{crew_id}/ui/...`, the transport SHALL check that
the request carries a valid `gs_session` cookie via `SessionStore.validate()`.
If the session is absent or invalid, the transport SHALL complete the ASGI
handshake with HTTP 401 (not a WebSocket upgrade). This closes the gap left by
the Caddy-layer bypass: even though the WebSocket route skips `forward_auth`, a
transport-layer check ensures unauthenticated WebSocket connections are refused.

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

## ADDED Requirements

### Requirement: Caddy admin API restricted to transport-origin requests
The Caddy `initial-config.json` written by `install.sh` SHALL include an
`"origins"` list in the `"admin"` object restricting which HTTP `Origin`
headers the admin API accepts. The list SHALL include only `http://ga-transport`
(the DNS name of the transport container on `ga-portside`). Requests from any
other origin SHALL be rejected by Caddy's built-in admin API enforcement.

The admin API bind address (`0.0.0.0:2019`) SHALL remain unchanged: it is
required for Caddy's own internal routing and the port is not published to the
host in `compose.yml`. The `origins` field is the enforcement mechanism.

#### Scenario: Transport can register a crew dashboard server
- **WHEN** the transport calls `PUT /config/apps/http/servers/crew-{crew_id}`
  on the Caddy admin API with `Origin: http://ga-transport`
- **THEN** Caddy accepts the request and the crew server is registered

#### Scenario: Request from another container is rejected
- **WHEN** a container other than `ga-transport` calls the Caddy admin API
  with an `Origin` header that is not `http://ga-transport`
- **THEN** Caddy returns 403 and does not apply the configuration change

#### Scenario: Admin API is not host-published
- **WHEN** `install.sh` generates `compose.yml`
- **THEN** `compose.yml` does not contain a `2019:2019` port mapping for `ga-portal`

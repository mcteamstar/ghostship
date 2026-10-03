## ADDED Requirements

### Requirement: WebSocket upgrades bypass forward_auth on the dashboard port

The per-crew Caddy dashboard server registered via `_caddy_register_crew` SHALL expose two routes rather than a single `forward_auth`-then-`reverse_proxy` route. A WebSocket upgrade request arriving on the crew's dashboard port (identified by a `Connection: Upgrade` request header) SHALL be matched by a dedicated route that proxies directly to the transport UI proxy WITHOUT invoking the `forward_auth` handler, so the upgrade handshake is preserved and the connection is upgraded. All non-upgrade (plain HTTP) requests SHALL continue to be matched by a catch-all route that invokes `forward_auth` ahead of the proxy, exactly as before.

Both routes SHALL inject the `X-Transport-Token` header on the request forwarded to `ga-transport`, and both SHALL dial `ga-transport:{PORT}` with the `/crews/{crew_id}/ui/{path}` rewrite. The WebSocket route SHALL be ordered before the catch-all HTTP route so that upgrade requests never fall through to the `forward_auth` path.

Bypassing `forward_auth` for WebSocket upgrades introduces no authentication regression: the browser can only reach the dashboard port after the initial SPA page load, whose plain-HTTP request was gated by `forward_auth` and validated the `gs_session`. The WebSocket connection inherits that authenticated browser context.

#### Scenario: WebSocket upgrade route is present and bypasses forward_auth

- **WHEN** `_caddy_register_crew` registers a per-crew dashboard server and an API key is configured
- **THEN** the registered server object contains a route whose matcher is `{"header": {"Connection": ["Upgrade"]}}`
- **THEN** that route's handler list contains the `reverse_proxy` handler and does NOT contain the `forward_auth` handler
- **THEN** the server object also contains a catch-all route (no matcher) whose handler list begins with the `forward_auth` handler followed by the `reverse_proxy` handler
- **THEN** the WebSocket route precedes the catch-all route in the server object's `routes` list

#### Scenario: SPA WebSocket connection is upgraded through the dashboard port

- **WHEN** the KiroCrew SPA opens a WebSocket connection (`Connection: Upgrade`) through a crew's dashboard port after the authenticated SPA page has loaded
- **THEN** Caddy matches the request on the `Connection: Upgrade` route and does not fire a `forward_auth` subrequest
- **THEN** the request is proxied to `ga-transport:{PORT}` with the `/crews/{crew_id}/ui/{path}` rewrite and the `X-Transport-Token` header injected
- **THEN** the connection completes the upgrade (HTTP 101 Switching Protocols) and the SPA sessions list and live updates function

#### Scenario: WebSocket route is registered even when no API key is set

- **WHEN** `_caddy_register_crew` registers a per-crew dashboard server and `self._api_key` is unset
- **THEN** the catch-all HTTP route contains only the `reverse_proxy` handler (no `forward_auth`)
- **THEN** the `Connection: Upgrade` WebSocket route is still present and also contains only the `reverse_proxy` handler

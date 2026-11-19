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

### Requirement: Gateway allowed-origins includes the crew's own hostname

When launching a crew, the transport SHALL patch `config.local.json` so the crew gateway's `dashboard.url` is set to its own internal container origin (`http://gs-{crew_id}:{CREW_GATEWAY_PORT}`). The gateway builds its `allowed_origins` set at startup from `dashboard.url`; without a configured value it falls back to loopback-only (`http://localhost:{PORT}`, `http://127.0.0.1:{PORT}`), which does not include the container hostname.

The transport's WS proxy injects `Origin: http://gs-{crew_id}:{CREW_GATEWAY_PORT}` on the upstream WebSocket handshake. The gateway's `check_origin` validation (invoked with `require=True` for WS upgrades) SHALL therefore accept that `Origin`, allowing the WebSocket upgrade to complete with `101 Switching Protocols` rather than being rejected with `403 WebSocket origin not allowed`.

This requirement constrains only the gateway's own origin. The `allowed_origins` set SHALL continue to exclude all external and attacker origins — the container hostname is an internal `ga-starboard` address, so no external origin becomes permissible.

#### Scenario: Launched crew config carries its own dashboard.url

- **WHEN** a crew is launched and the transport patches `config.local.json`
- **THEN** the patched config contains `dashboard.url` set to `http://gs-{crew_id}:{CREW_GATEWAY_PORT}` (e.g. `http://gs-alpha:5476`)
- **THEN** KiroCrew's deep-merge of `config.local.json` over `config.json` applies this value on every gateway start without any restart-logic change

#### Scenario: Gateway allowed-origins contains the container hostname

- **WHEN** the crew gateway builds its `allowed_origins` set at startup from the configured `dashboard.url`
- **THEN** the set includes `http://gs-{crew_id}:{CREW_GATEWAY_PORT}`
- **THEN** the set still excludes every external and attacker origin — only the gateway's own internal origin and the existing loopback origins are present

#### Scenario: WebSocket upgrade with proxied Origin is accepted

- **WHEN** the transport WS proxy opens the upstream handshake to `gs-{crew_id}:{CREW_GATEWAY_PORT}` carrying `Origin: http://gs-{crew_id}:{CREW_GATEWAY_PORT}`
- **THEN** the gateway's `_check_ws_origin` → `check_origin(request, require=True)` validation passes because the `Origin` is in `allowed_origins`
- **THEN** the gateway responds `101 Switching Protocols` and the WebSocket connects — it is NOT rejected with `403 WebSocket origin not allowed`

#### Scenario: Dashboard live features unlock over the connected socket

- **WHEN** the KiroCrew SPA's WebSocket connects successfully (101) through the dashboard port
- **THEN** the sessions list loads, live task updates stream, and the import modal can be dismissed normally — the behaviours previously blocked by the 403

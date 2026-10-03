## ADDED Requirements

### Requirement: Gateway allowed-origins includes the crew's own hostname

When launching a crew, the transport SHALL patch `config.local.json` so the
crew gateway's `dashboard.url` is set to its own internal container origin
(`http://gs-{crew_id}:{CREW_GATEWAY_PORT}`). The gateway builds its
`allowed_origins` set at startup from `dashboard.url`; without a configured
value it falls back to loopback-only
(`http://localhost:{PORT}`, `http://127.0.0.1:{PORT}`), which does not include
the container hostname.

The transport's WS proxy injects `Origin: http://gs-{crew_id}:{CREW_GATEWAY_PORT}`
on the upstream WebSocket handshake. The gateway's `check_origin` validation
(invoked with `require=True` for WS upgrades) SHALL therefore accept that
`Origin`, allowing the WebSocket upgrade to complete with `101 Switching
Protocols` rather than being rejected with `403 WebSocket origin not allowed`.

This requirement constrains only the gateway's own origin. The allowed-origins
set SHALL continue to exclude all external and attacker origins — the
container hostname is reachable only from inside `ga-net` via the transport,
so no external origin becomes permissible.

#### Scenario: Launched crew config carries its own dashboard.url

- **WHEN** a crew is launched and the transport patches `config.local.json`
- **THEN** the patched config contains `dashboard.url` set to
  `http://gs-{crew_id}:{CREW_GATEWAY_PORT}` (e.g. `http://gs-alpha:5476`)
- **THEN** KiroCrew's deep-merge of `config.local.json` over `config.json`
  applies this value on every gateway start without any restart-logic change

#### Scenario: Gateway allowed-origins contains the container hostname

- **WHEN** the crew gateway builds its `allowed_origins` set at startup from
  the configured `dashboard.url`
- **THEN** the set includes `http://gs-{crew_id}:{CREW_GATEWAY_PORT}`
- **THEN** the set still excludes every external and attacker origin — only
  the gateway's own internal origin and the existing loopback origins are
  present

#### Scenario: WebSocket upgrade with proxied Origin is accepted

- **WHEN** the transport WS proxy opens the upstream handshake to
  `gs-{crew_id}:{CREW_GATEWAY_PORT}` carrying
  `Origin: http://gs-{crew_id}:{CREW_GATEWAY_PORT}`
- **THEN** the gateway's `_check_ws_origin` → `check_origin(request,
  require=True)` validation passes because the `Origin` is in
  `allowed_origins`
- **THEN** the gateway responds `101 Switching Protocols` and the WebSocket
  connects — it is NOT rejected with `403 WebSocket origin not allowed`

#### Scenario: Dashboard live features unlock over the connected socket

- **WHEN** the KiroCrew SPA's WebSocket connects successfully (101) through
  the dashboard port
- **THEN** the sessions list loads, live task updates stream, and the import
  modal can be dismissed normally — the behaviours previously blocked by the
  403

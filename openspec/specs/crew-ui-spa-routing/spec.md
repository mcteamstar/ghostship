# crew-ui-spa-routing Specification

## Purpose

Serve each crew's browser dashboard through a Portal-managed port, with the transport proxying UI and WebSocket traffic to the crew gateway. The SPA owns its origin so assets, client-side routing, and hard reloads work correctly; dashboard messages are read through REST.

## Requirements

### Requirement: Each crew dashboard is served through Portal on a unique UI port

When launched with `dashboard=true`, the transport SHALL allocate and store a unique port from the configured range, register it with Portal (Caddy), and return it as `dashboard_url`. Portal SHALL forward requests on that port to the transport's `/crews/{crew_id}/ui` proxy, which SHALL forward HTTP and WebSocket traffic to `http://gs-{crew_id}:5476/{path}`. The transport SHALL NOT start a per-port listener.

#### Scenario: SPA loads at root of origin
- **WHEN** a browser opens `<scheme>://ghostship-host.example.ts.net:64058/`, where the scheme follows Portal's configured TLS mode
- **THEN** Portal forwards the request to `ga-transport` at `/crews/my-crew/ui/`, the transport proxies to `http://gs-my-crew:5476/`, and the SPA loads correctly

#### Scenario: Client-side navigation and hard reload both work
- **WHEN** the SPA navigates to `/chat` and the user hard-reloads
- **THEN** `<scheme>://ghostship-host.example.ts.net:64058/chat` is forwarded by Portal to the transport's `/crews/my-crew/ui/chat` proxy, then to `http://gs-my-crew:5476/chat`, and the SPA renders correctly

#### Scenario: WebSocket connection proxied to upstream
- **WHEN** the SPA opens a WebSocket connection to the dashboard's `/api/ws` path
- **THEN** Portal forwards the upgrade to the transport's `/crews/my-crew/ui/api/ws` route, which bidirectionally proxies messages to `ws://gs-my-crew:5476/api/ws`

#### Scenario: Dashboard session auth applies to UI traffic
- **WHEN** `GA_API_KEY` is set and a browser request through Portal has no valid `gs_session` cookie
- **THEN** Portal's forward-auth check or the transport's WebSocket session check rejects the request before it reaches the crew gateway

#### Scenario: Launch returns dashboard_url
- **WHEN** `launch` is called for crew `my-crew` with `dashboard=True`
- **THEN** the response includes `dashboard_url: "http://<host>:64058/"`

#### Scenario: Launch without dashboard returns null dashboard_url
- **WHEN** `launch` is called without `dashboard=True` (default)
- **THEN** the response includes `dashboard_url: null` and no port is allocated

#### Scenario: Port released at nuke
- **WHEN** `nuke` is called for a crew that has an allocated dashboard port
- **THEN** the Portal registration is removed and the port is returned to the pool

#### Scenario: Port range exhausted
- **WHEN** `launch(dashboard=True)` is called and all ports in the range are already allocated
- **THEN** `launch` returns an error indicating the dashboard port pool is exhausted

### Requirement: Portal dashboard registrations restored on transport restart

On startup, the transport SHALL restore each allocated port and re-register crews with a `dashboard_port` in the registry with Portal (Caddy), restoring UI access after a transport restart without starting per-port transport listeners.

#### Scenario: Portal registrations restored after transport restart
- **WHEN** the transport restarts and a crew has a `dashboard_port` in the registry
- **THEN** the transport restores its port mapping and registers the crew with Portal before accepting requests

### Requirement: crews list includes dashboard_url per crew

The `crews` tool response SHALL include `dashboard_url` for each crew that has an allocated port. `dashboard_url` SHALL be `null` for crews without a port assignment.

#### Scenario: crews response includes dashboard_url
- **WHEN** `crews` is called and a crew has an allocated `dashboard_port`
- **THEN** that crew's entry includes `dashboard_url` as a non-null string

#### Scenario: crews response includes null dashboard_url for headless crew
- **WHEN** `crews` is called and a crew has no `dashboard_port`
- **THEN** that crew's entry includes `dashboard_url: null`

### Requirement: Transport strips Accept-Encoding from crew proxy requests

The crew UI proxy MUST remove `Accept-Encoding` from outbound requests and `Content-Encoding` from responses. It streams raw bytes without decompression; forwarded compression would leave the browser unable to decode the response.

#### Scenario: Crew gateway always receives uncompressed request

- **WHEN** a browser sends `GET /crews/{id}/ui/assets/main.js` with `Accept-Encoding: gzip, br`
- **THEN** the transport forwards the request to the crew gateway WITHOUT an `Accept-Encoding` header
- **AND** the crew gateway returns an uncompressed response
- **AND** the browser successfully parses the JS asset

#### Scenario: Asset response is valid JS, not binary

- **GIVEN** a running crew with a dashboard port
- **WHEN** `GET /crews/{id}/ui/assets/main.js` is proxied through the transport
- **THEN** the response body starts with valid JS text (e.g. `const `)
- **AND** the response does NOT contain gzip magic bytes (`0x1f 0x8b`)

### Requirement: Portal reads message content from REST, not WebSocket payload bodies

The portal SHALL read assistant text, tool titles, and tool output only from `GET /api/sessions/{id}/messages`. WebSocket messages MAY signal session-state changes, but the portal SHALL NOT rely on non-user content fields in WS payloads.

#### Scenario: Full message content rendered despite WS broadcast redaction
- **WHEN** the upstream crew gateway strips `assistant_content` and `tool_title` from WS broadcast payloads (as in KiroCrew 0.9.0+)
- **THEN** the portal still renders complete assistant text and tool-call content, sourced from `GET /api/sessions/{id}/messages` via REST

#### Scenario: WS messages used only for lifecycle notifications
- **WHEN** a crew session is active and the upstream gateway emits WS session-state events (turn started, turn ended, new message)
- **THEN** the portal updates its live-session state indicators based on those WS signals

#### Scenario: Portal does not break when WS payload drops assistant_content
- **WHEN** a WS broadcast payload for a completed turn contains no `assistant_content` field
- **THEN** the portal produces no console error referencing `assistant_content` and displays the turn's content fetched from REST

#### Scenario: Portal does not break when WS payload drops tool_title
- **WHEN** a WS broadcast payload for a tool-call event contains no `tool_title` field
- **THEN** the portal produces no console error referencing `tool_title` and displays the tool-call title fetched from REST

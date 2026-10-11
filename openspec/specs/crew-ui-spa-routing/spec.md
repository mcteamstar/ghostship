# crew-ui-spa-routing Specification

## Purpose

Enable the KiroCrew gateway SPA to load and navigate correctly when accessed via the transport, by giving each crew a dedicated port on the transport. The SPA owns its entire origin so assets, client-side routing, and hard reloads all work correctly. All traffic is handled by the transport, so existing security policies apply uniformly.

## Requirements

### Requirement: Each crew is assigned a unique UI port on the transport at launch

The transport SHALL allocate a unique port from the configured range (`GA_DASHBOARD_PORT_RANGE_START` to `GA_DASHBOARD_PORT_RANGE_START + GA_DASHBOARD_PORT_RANGE_SIZE - 1`) when a crew is launched with `dashboard=true` and start a transport listener on that port. All requests arriving on that port SHALL be reverse-proxied to `http://gs-{crew_id}:5476/{path}`. WebSocket upgrade requests SHALL be bidirectionally proxied to the upstream crew gateway via `httpx-ws`. The allocated port SHALL be stored in the crew registry and returned in the `launch` response as `dashboard_url`.

#### Scenario: SPA loads at root of origin
- **WHEN** a browser opens `http://ghostship-host.example.ts.net:64058/`
- **THEN** the transport proxies to `http://gs-my-crew:5476/` and the SPA loads correctly

#### Scenario: Client-side navigation and hard reload both work
- **WHEN** the SPA navigates to `/chat` and the user hard-reloads
- **THEN** `http://ghostship-host.example.ts.net:64058/chat` is handled by the transport, proxied to `http://gs-my-crew:5476/chat`, and the SPA renders correctly

#### Scenario: WebSocket connection proxied to upstream
- **WHEN** the SPA opens a WebSocket connection to `ws://ghostship-host.example.ts.net:64058/api/ws`
- **THEN** the transport upgrades the connection and bidirectionally proxies messages to `ws://gs-my-crew:5476/api/ws`

#### Scenario: GA_API_KEY auth applies to UI port traffic
- **WHEN** `GA_API_KEY` is set and a request to the crew UI port omits or supplies an incorrect `Authorization: Bearer` header
- **THEN** the transport returns HTTP 401 before proxying, consistent with all other authenticated routes

#### Scenario: Launch returns dashboard_url
- **WHEN** `launch` is called for crew `my-crew` with `dashboard=True`
- **THEN** the response includes `dashboard_url: "http://<host>:64058/"`

#### Scenario: Launch without dashboard returns null dashboard_url
- **WHEN** `launch` is called without `dashboard=True` (default)
- **THEN** the response includes `dashboard_url: null` and no port is allocated

#### Scenario: Port released at nuke
- **WHEN** `nuke` is called for a crew that has an allocated dashboard port
- **THEN** the transport listener on the allocated port is stopped and the port is returned to the pool

#### Scenario: Port range exhausted
- **WHEN** `launch(dashboard=True)` is called and all ports in the range are already allocated
- **THEN** `launch` returns an error indicating the dashboard port pool is exhausted

### Requirement: Transport UI port listeners restored on restart

On startup, the transport SHALL re-start listeners for any crews that have a `dashboard_port` in the registry, restoring UI access for running crews after a transport restart.

#### Scenario: Listeners restored after transport restart
- **WHEN** the transport restarts and a crew has a `dashboard_port` in the registry
- **THEN** the transport starts a proxy listener on that port before accepting requests

### Requirement: crews list includes dashboard_url per crew

The `crews` tool response SHALL include `dashboard_url` for each crew that has an allocated port. `dashboard_url` SHALL be `null` for crews without a port assignment.

#### Scenario: crews response includes dashboard_url
- **WHEN** `crews` is called and a crew has an allocated `dashboard_port`
- **THEN** that crew's entry includes `dashboard_url` as a non-null string

#### Scenario: crews response includes null dashboard_url for headless crew
- **WHEN** `crews` is called and a crew has no `dashboard_port`
- **THEN** that crew's entry includes `dashboard_url: null`

### Requirement: GA_DASHBOARD_PORT_ENABLED flag

When `GA_DASHBOARD_PORT_ENABLED=false`, the transport SHALL skip all port allocation and listener management. Default is `true`.

#### Scenario: Feature disabled skips port allocation
- **WHEN** `GA_DASHBOARD_PORT_ENABLED=false` and `launch(dashboard=True)` is called
- **THEN** no port is allocated and `dashboard_url` is `null` in the response

### Requirement: Portal reads message content from REST, not WebSocket payload bodies

The ghostship portal SHALL read message content (assistant text, tool-call titles, tool output) exclusively from the REST API (`GET /api/sessions/{id}/messages`). The portal MAY consume WebSocket messages only for session-state change notifications (turn started, turn ended, new-message signal). The portal SHALL NOT depend on `assistant_content`, `tool_title`, or any other non-user content field being present in WebSocket broadcast payloads. This separation ensures that upstream WS broadcast redaction of non-user content is invisible to the portal.

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
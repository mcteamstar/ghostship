# crew-ui-spa-routing Specification

## Purpose

Enable the KiroCrew gateway SPA to load and navigate correctly when accessed via the transport, by giving each crew a dedicated port on the transport. The SPA owns its entire origin so assets, client-side routing, and hard reloads all work correctly. All traffic is handled by the transport, so existing security policies apply uniformly.

## Requirements

### Requirement: Each crew is assigned a unique UI port on the transport at launch

The transport SHALL allocate a unique port from the configured range (`GA_UI_PORT_RANGE_START` to `GA_UI_PORT_RANGE_START + GA_UI_PORT_RANGE_SIZE - 1`) when a crew is launched and start a transport listener on that port. All requests arriving on that port SHALL be reverse-proxied to `http://gs-{crew_id}:5476/{path}`. The allocated port SHALL be stored in the crew registry and returned in the `launch` response as `ui_url`.

#### Scenario: SPA loads at root of origin
- **WHEN** a browser opens `http://academy.penguin-piano.ts.net:64058/`
- **THEN** the transport proxies to `http://gs-my-crew:5476/` and the SPA loads correctly

#### Scenario: Client-side navigation and hard reload both work
- **WHEN** the SPA navigates to `/chat` and the user hard-reloads
- **THEN** `http://academy.penguin-piano.ts.net:64058/chat` is handled by the transport, proxied to `http://gs-my-crew:5476/chat`, and the SPA renders correctly

#### Scenario: GA_API_KEY auth applies to UI port traffic
- **WHEN** `GA_API_KEY` is set and a request to the crew UI port omits or supplies an incorrect `Authorization: Bearer` header
- **THEN** the transport returns HTTP 401 before proxying, consistent with all other authenticated routes

#### Scenario: Launch returns ui_url
- **WHEN** `launch` is called for crew `my-crew`
- **THEN** the response includes `ui_url: "http://<host>:64058/"`

#### Scenario: Port released at nuke
- **WHEN** `nuke` is called for a crew
- **THEN** the transport listener on the allocated port is stopped and the port is returned to the pool

#### Scenario: Port range exhausted
- **WHEN** `launch` is called and all ports in the range are already allocated
- **THEN** `launch` returns an error indicating the UI port pool is exhausted

### Requirement: Transport UI port listeners restored on restart

On startup, the transport SHALL re-start listeners for any crews that have a `ui_port` in the registry, restoring UI access for running crews after a transport restart.

### Requirement: crews list includes ui_url per crew

The `crews` tool response SHALL include `ui_url` for each crew that has an allocated port. `ui_url` SHALL be `null` for crews without a port assignment.

### Requirement: GA_UI_PORT_ENABLED flag

When `GA_UI_PORT_ENABLED=false`, the transport SHALL skip all port allocation and listener management. Default is `true`.

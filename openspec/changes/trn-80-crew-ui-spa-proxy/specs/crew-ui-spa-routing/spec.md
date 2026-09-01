# crew-ui-spa-routing Specification

## Purpose

Give each crew's UI a dedicated host port so the SPA owns its entire origin, enabling correct asset loading, client-side navigation, hard reloads, and WebSocket connections without path-prefix complications.

## Requirements

### Requirement: Each crew is assigned a unique UI host port at launch

The transport SHALL allocate a unique host port from the configured range (`GA_UI_PORT_RANGE_START` to `GA_UI_PORT_RANGE_START + GA_UI_PORT_RANGE_SIZE - 1`) when a crew is launched. The port SHALL be bound to the crew container's internal gateway port (5476) via a host port binding. The allocated port SHALL be stored in the crew's registry entry and returned in the `launch` response as `ui_url`.

#### Scenario: Launch allocates and returns ui_url
- **WHEN** `launch` is called for crew `my-crew`
- **THEN** the response includes `ui_url: "http://<host>:<port>/"` where `<port>` is the allocated host port

#### Scenario: SPA loads at root of origin
- **WHEN** a browser opens `http://academy.penguin-piano.ts.net:9001/`
- **THEN** the SPA loads from the crew gateway directly, with no path prefix, and all root-absolute asset paths resolve correctly

#### Scenario: Client-side navigation and hard reload both work
- **WHEN** the SPA navigates to `/chat` and the user hard-reloads
- **THEN** `http://academy.penguin-piano.ts.net:9001/chat` is served by the crew gateway and the SPA renders correctly

#### Scenario: Port range exhausted
- **WHEN** `launch` is called and all ports in the range are already allocated
- **THEN** `launch` returns an error indicating the UI port pool is exhausted

#### Scenario: Port released at nuke
- **WHEN** `nuke` is called for a crew
- **THEN** the allocated host port is released back to the pool and available for the next launch

### Requirement: crews list includes ui_url per crew

The `crews` tool response SHALL include `ui_url` for each crew that has an allocated port. `ui_url` SHALL be `null` for crews without a port assignment (launched before this change or with `GA_UI_PORT_ENABLED=false`).

### Requirement: GA_UI_PORT_ENABLED flag

When `GA_UI_PORT_ENABLED=false`, the transport SHALL skip port allocation and fall back to the existing Python-layer `_handle_crew_ui_proxy`. Default is `true`.

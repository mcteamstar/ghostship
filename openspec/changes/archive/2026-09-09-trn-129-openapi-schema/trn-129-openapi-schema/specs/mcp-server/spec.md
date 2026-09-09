## MODIFIED Requirements

### Requirement: Tool surface covers the full crew lifecycle
The system SHALL expose exactly these tools to MCP clients, grouped and ordered by what they operate on — workspace tools first (`crews`, `launch`, `supply`, `evac`, `nuke`), then agent tools (`captain`, `dispatch`, `schedule`, `steer`, `pickup`, `bridge`) — covering creation, file exchange, teardown, autonomous and manual task orchestration, and blocking task waits.

The transport SHALL also expose `GET /openapi.json` as part of its public HTTP surface. This route is listed in the transport spec (`trn-openapi-schema`) and is not a new MCP tool, but its existence is part of the transport's documented public surface.

#### Scenario: Tool discovery
- **WHEN** an MCP client lists tools on the `ghostship` connection
- **THEN** it sees all eleven tools above, in that order, and no others, including `bridge` with the docstring-derived description used for model tool selection

#### Scenario: OpenAPI schema discoverable without MCP client
- **WHEN** an HTTP GET request is made to `/openapi.json` on the transport port
- **THEN** the response is a valid OpenAPI 3.x JSON document describing the transport's full HTTP surface, accessible without an MCP client or authentication

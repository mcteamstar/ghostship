## MODIFIED Requirements

### Requirement: User-facing error messages on recovery failure
The system SHALL return human-readable, actionable error messages to MCP clients when crew recovery fails, replacing raw HTTP status codes with messages that state the crew identifier, what recovery was attempted, and a suggested next action.

#### Scenario: Stale-cookie recovery failure surfaces actionable message
- **WHEN** an MCP tool call to a crew fails after the transport exhausted cookie-refresh and restart recovery
- **THEN** the MCP error response includes a message like "crew <crew_id> is unresponsive — the transport attempted recovery but the gateway did not come back. Try calling again in a moment or check crew status with crews()." rather than a raw 400/500 status code

#### Scenario: Connection-error recovery failure surfaces actionable message
- **WHEN** an MCP tool call to a crew fails due to a connection error after the transport attempted a restart
- **THEN** the MCP error response includes a message identifying the crew, stating restart was attempted, and suggesting the caller retry or inspect the crew

#### Scenario: Error messages do not leak implementation details
- **WHEN** recovery-failure errors are returned to the MCP client
- **THEN** messages do not include raw HTTP response bodies, Python tracebacks, container names (beyond crew_id), or internal endpoint paths

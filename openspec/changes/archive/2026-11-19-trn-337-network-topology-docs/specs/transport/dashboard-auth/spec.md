# Spec Delta

## MODIFIED Requirements

### Requirement: MCP/API auth posture

Caddy SHALL be the first auth gate for all traffic — Bearer enforcement for MCP/files at the edge and `forward_auth` for dashboards. `BearerAuthMiddleware` SHALL remain active as defence in depth for requests that reach the transport directly over `ga-portside` or `ga-starboard`.

#### Scenario: Caddy is the first gate for all traffic

- **WHEN** `GA_API_KEY` is set
- **THEN** an unauthenticated MCP or dashboard request is rejected by Caddy before reaching the transport
- **THEN** the transport's `BearerAuthMiddleware` still runs for requests that reach it directly over `ga-portside` or `ga-starboard`

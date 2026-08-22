## MODIFIED Requirements

### Requirement: Host memory visibility in crews() response

The `crews()` MCP endpoint SHALL include a top-level
`host_memory_available_gb` field (float, rounded to 1 decimal) in its JSON
response, representing the current available memory as reported by the Podman
info API.

The value SHALL be cached for up to 5 seconds to avoid per-call Podman API
overhead.

#### Scenario: crews() returns memory field
- **WHEN** a client calls the `crews()` endpoint
- **THEN** the response includes `"host_memory_available_gb": <float>` at the top level alongside the crew list

#### Scenario: Cached value within TTL
- **WHEN** two `crews()` calls are made within 5 seconds
- **THEN** only one Podman info API call is made; the second response uses the cached value

#### Scenario: Podman info unavailable
- **WHEN** the Podman info API call fails
- **THEN** `host_memory_available_gb` is set to `null` and the rest of the response is unaffected

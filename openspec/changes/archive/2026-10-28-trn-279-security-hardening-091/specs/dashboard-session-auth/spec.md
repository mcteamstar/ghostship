# Spec Delta

## ADDED Requirements

### Requirement: Forward_auth port parameter is validated against the configured range
The `/dashboard/auth` forward_auth endpoint SHALL reject any `port` query parameter value that does not fall within the configured dashboard port range (`ga_dashboard_port_base` through `ga_dashboard_port_base + ga_dashboard_port_range_size - 1`, inclusive). A request with a `port` value outside this range SHALL receive HTTP 400 without performing a crew lookup. A request with a `port` value inside the range that does not map to any known crew SHALL receive HTTP 200 (valid session, no crew-specific cookie injection needed).

#### Scenario: Port below the configured range is rejected
- **WHEN** `GET /dashboard/auth` is called with a `port` query parameter whose integer value is less than `ga_dashboard_port_base`
- **THEN** the transport returns HTTP 400 without performing a crew lookup

#### Scenario: Port above the configured range is rejected
- **WHEN** `GET /dashboard/auth` is called with a `port` query parameter whose integer value is greater than or equal to `ga_dashboard_port_base + ga_dashboard_port_range_size`
- **THEN** the transport returns HTTP 400 without performing a crew lookup

#### Scenario: Port within the configured range proceeds normally
- **WHEN** `GET /dashboard/auth` is called with a `port` query parameter whose integer value is within the configured range
- **THEN** the transport proceeds to crew lookup; a valid session returns HTTP 200 regardless of whether the port maps to a known crew

#### Scenario: Missing port parameter is not rejected
- **WHEN** `GET /dashboard/auth` is called with no `port` query parameter
- **THEN** the transport does not return HTTP 400; it falls back to other port-resolution methods (e.g. `x-dashboard-port` header)

#### Scenario: Non-integer port parameter is rejected
- **WHEN** `GET /dashboard/auth` is called with a `port` query parameter that is not a valid integer (e.g. `port=abc`)
- **THEN** the transport returns HTTP 400 without performing a crew lookup

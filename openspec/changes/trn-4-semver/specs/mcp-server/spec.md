## ADDED Requirements

### Requirement: Version resource exposes transport and crew image versions
The system SHALL expose a `transport://version` MCP resource that returns the transport process version and, for each running crew, the crew image version. The transport version SHALL be read from a `VERSION` file at the repository root at startup. The crew image version SHALL be read from the crew container's OCI label `org.ghostship.version` at crew launch time and stored in the registry.

#### Scenario: Version resource with no crews running
- **WHEN** `transport://version` is read and no crews are registered
- **THEN** the response is a JSON object containing `transport` set to the semver string from the `VERSION` file, and `crews` as an empty object

#### Scenario: Version resource with crews running
- **WHEN** `transport://version` is read and one or more crews are registered
- **THEN** the response is a JSON object containing `transport` set to the transport semver, and `crews` as an object keyed by `crew_id` each with a `crew_image_version` field read from the registry

#### Scenario: VERSION file missing at startup
- **WHEN** the transport process starts and no `VERSION` file exists at the repository root
- **THEN** the transport version SHALL default to `"0.0.0-dev"` and the resource SHALL still be available

#### Scenario: Crew image has no version label
- **WHEN** a crew is launched from an image that does not carry the `org.ghostship.version` OCI label
- **THEN** the registry stores `crew_image_version` as `"unknown"` for that crew, and `transport://version` reports it as such

### Requirement: HTTP health endpoint includes version
The system SHALL include the transport version in the MCP server's HTTP response headers or a dedicated `GET /version` route on the MCP port, so that monitoring tools and operators can query the running version without an MCP client.

#### Scenario: GET /version returns JSON
- **WHEN** an HTTP GET request is made to `/version` on the MCP port
- **THEN** the response is `200 OK` with `Content-Type: application/json` and a body containing at minimum `{"transport": "<semver>"}`

#### Scenario: Unauthenticated access when API key is set
- **WHEN** `GA_API_KEY` is configured and a GET request to `/version` omits the bearer token
- **THEN** the response is `200 OK` — the version endpoint SHALL NOT require authentication, as version information is not sensitive

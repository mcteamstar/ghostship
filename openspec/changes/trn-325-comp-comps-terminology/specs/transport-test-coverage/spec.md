# Spec Delta

## MODIFIED Requirements

### Requirement: Crew registry key compatibility has test coverage
The test suite SHALL cover canonical `comps` loading, the legacy `compositions` alias, matching dual keys, and conflicting dual keys.

#### Scenario: Canonical comps key is loaded
- **WHEN** a registry fixture contains a valid `comps` key
- **THEN** the test verifies all configured comps are available

#### Scenario: Legacy compositions key is loaded
- **WHEN** a registry fixture contains only `compositions`
- **THEN** the test verifies all configured comps are available

#### Scenario: Matching registry keys are accepted
- **WHEN** a registry fixture contains both keys with equal entries
- **THEN** the test verifies the entries are loaded once

#### Scenario: Conflicting registry keys prefer comps
- **WHEN** a registry fixture contains both keys with different entries
- **THEN** the test verifies the `comps` entries are loaded and `compositions` is ignored

### Requirement: Launch alias resolution has test coverage
The test suite SHALL cover canonical `comp`, legacy `composition`, matching dual values, conflicting values, and the default when neither argument is supplied.

#### Scenario: Canonical comp launches a crew
- **WHEN** launch is called with a valid `comp`
- **THEN** the test verifies the matching registry entry is used

#### Scenario: Legacy composition alias launches a crew
- **WHEN** launch is called with `composition` and no `comp`
- **THEN** the test verifies the matching registry entry is used

#### Scenario: Matching comp aliases launch a crew
- **WHEN** launch is called with equal `comp` and `composition` values
- **THEN** the test verifies the matching registry entry is used

#### Scenario: Conflicting comp aliases use comp
- **WHEN** launch is called with different `comp` and `composition` values
- **THEN** the test verifies `comp` is resolved and a warning is logged

#### Scenario: Omitted comp arguments use the default
- **WHEN** launch is called without either argument
- **THEN** the test verifies the default `"spec-ops"` entry is used

### Requirement: Crew persistence and MCP payload compatibility have test coverage
The test suite SHALL verify that canonical and legacy persisted fields are resolved consistently and that MCP crew payload aliases carry equal values.

#### Scenario: New crew records contain canonical comp and alias
- **WHEN** a crew record is written for `comp="spec-ops"`
- **THEN** the test verifies both `comp` and `composition` contain `"spec-ops"`

#### Scenario: Legacy-only record resolves comp
- **WHEN** a persisted record contains only `composition`
- **THEN** the test verifies the loaded crew and MCP response expose that value as both fields

#### Scenario: Conflicting persisted fields normalize to comp
- **WHEN** a persisted record contains different `comp` and `composition` values
- **THEN** the test verifies a mismatch is logged and the MCP response emits both fields using `comp`

### Requirement: Comp discovery resource aliases have test coverage
The test suite SHALL verify that both discovery URIs are registered, readable, and return identical comp listings.

#### Scenario: Canonical comps resource is discoverable
- **WHEN** resource discovery is requested
- **THEN** the test verifies `transport://comps` is listed and returns available comps

#### Scenario: Legacy compositions resource remains discoverable
- **WHEN** resource discovery is requested during the rollback window
- **THEN** the test verifies `transport://compositions` is listed and returns content identical to `transport://comps`

### Requirement: REST crew payload compatibility has test coverage
The test suite SHALL verify that REST crew records expose canonical `comp`, a same-value `composition` alias, and values matching MCP output.

#### Scenario: REST and MCP crew fields match
- **WHEN** the REST endpoint and MCP `crews()` tool return the same fleet state
- **THEN** the test verifies each crew has equal `comp` and `composition` values in both responses

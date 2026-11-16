# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: Base crew image built before composition images`
- TO: `### Requirement: Base crew image built before comp images`

## MODIFIED Requirements

### Requirement: Base crew image built before comp images
`install.sh` SHALL build `localhost/base:latest` from `crews/_base/Containerfile` before building any comp image. The `_base` directory is an internal build dependency and SHALL NOT appear as a comp in `crews/registry.json`.

#### Scenario: Fresh install builds base then spec-ops
- **WHEN** `install.sh` runs
- **THEN** it builds `localhost/base:latest` first, then builds `localhost/spec-ops:latest` from that base

#### Scenario: _base not exposed as a comp
- **WHEN** a client calls `crews()` or reads `transport://comps`
- **THEN** `_base` does not appear as an available comp

### Requirement: transport://comps is the canonical discovery resource
The system SHALL expose `transport://comps` as the canonical MCP resource for listing available crew comps. The legacy `transport://compositions` URI SHALL remain an alias that returns identical content during the rollback window.

#### Scenario: transport://comps lists available comps
- **WHEN** a client reads `transport://comps`
- **THEN** the response lists each available comp with its name, description, and optional image override, and the resource name and title use “comps”

#### Scenario: Legacy compositions URI remains readable
- **WHEN** a client reads `transport://compositions` during the rollback window
- **THEN** the response is identical to `transport://comps` and lists the same available comps

# Spec Delta

## MODIFIED Requirements

### Requirement: Launch resolves crew type
The `launch` tool SHALL accept canonical `comp` and the legacy `composition` alias, resolve the effective value from the crew registry, and use that entry's image and directory when creating the crew. Conflicting values SHALL return a clear error without creating a crew; if neither is supplied, the default SHALL be `"spec-ops"`.

#### Scenario: Launch with default crew type
- **WHEN** `launch` is called without `comp` or `composition`
- **THEN** the system launches using the `"spec-ops"` entry

#### Scenario: Launch with explicit crew type
- **WHEN** `launch` is called with `comp="worker"`
- **THEN** the system resolves the `"worker"` entry and uses its image and manifest path

#### Scenario: Launch with legacy composition alias
- **WHEN** `launch` is called with `composition="worker"` and no `comp`
- **THEN** the system resolves the `"worker"` entry and uses its image and manifest path

#### Scenario: Matching comp and composition values
- **WHEN** `launch` is called with `comp="worker"` and `composition="worker"`
- **THEN** the system resolves the `"worker"` entry and uses its image and manifest path

#### Scenario: Conflicting comp and composition values
- **WHEN** `launch` is called with `comp="worker"` and `composition="spec-ops"`
- **THEN** the system returns an error naming both values and available comps and creates no crew

#### Scenario: Launch with unknown crew type
- **WHEN** `launch` is called with a value not present in the loaded registry
- **THEN** the system returns an error naming the unknown value and listing available comps

### Requirement: Crew type stored in registry entry
The system SHALL store the canonical `comp` in each crew record and expose it to downstream consumers. During the rollback window, `composition` SHALL be retained as a same-value compatibility alias. Readers SHALL accept legacy records containing only `composition`; when both fields differ, `comp` SHALL be authoritative, the mismatch SHALL be logged, and subsequent serialization SHALL write both fields with the `comp` value.

#### Scenario: Registry entry includes crew type
- **WHEN** a crew is launched with `comp="review"`
- **THEN** its record includes `"comp": "review"` and `"composition": "review"`

#### Scenario: Legacy record contains only composition
- **WHEN** the system reads a pre-migration crew record containing only `"composition": "review"`
- **THEN** it resolves the crew's `comp` as `"review"` and emits both fields with that value on serialization

#### Scenario: Conflicting persisted fields use comp as authoritative
- **WHEN** the system reads a crew record containing `"comp": "spec-ops"` and `"composition": "worker"`
- **THEN** it logs the mismatch and subsequent serialization emits both fields as `"spec-ops"`

#### Scenario: Existing crews without type field
- **WHEN** the system reads a pre-migration record with neither `comp` nor `composition`
- **THEN** it treats the crew as `"spec-ops"` for display and operational purposes

### Requirement: Crew-type registry file
The system SHALL load crew entries from `crews/registry.json` using canonical key `comps` and SHALL continue accepting legacy key `compositions` during the rollback window. Each entry maps a comp name to its configuration. If both keys are present, equal values SHALL be treated as one registry and different values SHALL produce a clear startup configuration error.

#### Scenario: Registry lists available types
- **WHEN** `crews/registry.json` contains a valid `comps` key
- **THEN** the system loads all entries and makes them available for launch and discovery

#### Scenario: Registry accepts legacy compositions key
- **WHEN** `crews/registry.json` contains `compositions` and no `comps` key
- **THEN** the system loads those entries and makes them available for launch and discovery

#### Scenario: Registry accepts matching keys
- **WHEN** `crews/registry.json` contains both keys with equal values
- **THEN** the system treats them as one registry and loads each entry once

#### Scenario: Registry rejects conflicting keys
- **WHEN** `crews/registry.json` contains both keys with different values
- **THEN** startup fails with a clear configuration error naming the conflict

#### Scenario: Registry is missing
- **WHEN** `crews/registry.json` does not exist
- **THEN** the system falls back to the single implicit `"spec-ops"` entry with current hardcoded defaults (`KC_IMAGE`, `crews/spec-ops/manifest.json`, `crews/spec-ops/Containerfile`)

#### Scenario: Registry entry references a nonexistent directory
- **WHEN** a crew entry points to a `crews/<name>/` directory that does not exist
- **THEN** the system logs a warning and excludes that entry from the available set

## REMOVED Requirements

### Requirement: Crew-type discovery tool
**Reason**: The current transport does not expose a `crew_types` MCP tool; available comps are discovered through the MCP resource contract.
**Migration**: Clients use `transport://comps`. The legacy `transport://compositions` URI remains readable as a compatibility alias during the rollback window.

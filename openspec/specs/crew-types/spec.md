# crew-types Specification

## Purpose

Defines how comps are declared, discovered, validated, and resolved at launch time, so each crew can use configured agents, skills, steering, and images without code changes to the transport server.

## Requirements

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

#### Scenario: Registry prefers comps on conflicting keys
- **WHEN** `crews/registry.json` contains both keys with different values
- **THEN** the system loads the `comps` entries, ignores `compositions`, and logs a warning naming the conflict

#### Scenario: Registry falls back to legacy key when comps is not a list
- **WHEN** `crews/registry.json` contains a `comps` key that is not a list and a valid `compositions` list
- **THEN** the system loads the `compositions` entries and logs a warning

#### Scenario: Registry is missing
- **WHEN** `crews/registry.json` does not exist
- **THEN** the system falls back to the single implicit `"spec-ops"` entry with current hardcoded defaults (`KC_IMAGE`, `crews/spec-ops/manifest.json`, `crews/spec-ops/Containerfile`)

#### Scenario: Registry entry references a nonexistent directory
- **WHEN** a comp entry points to a `crews/<name>/` directory that does not exist
- **THEN** the system logs a warning and excludes that entry from the available set

### Requirement: Crew-type definition schema

Each comp entry in `crews/registry.json` SHALL contain: `name` (string, kebab-case, 1-50 chars), `description` (string), `image` (optional string — container image override; defaults to `KC_IMAGE`), and `dir` (string — relative path under `crews/` containing the comp's `manifest.json` and `Containerfile`).

#### Scenario: Minimal valid entry
- **WHEN** a registry entry specifies only `name`, `description`, and `dir`
- **THEN** the system uses the global `KC_IMAGE` default for that comp's container image and resolves `manifest.json` from the specified `dir`

#### Scenario: Entry with image override
- **WHEN** a registry entry includes an `image` field
- **THEN** the system uses that image when launching crews of this comp instead of the global `KC_IMAGE`

#### Scenario: Invalid name format
- **WHEN** a registry entry's `name` does not match `^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$` (or single char `^[a-z0-9]$`)
- **THEN** the system logs a warning and excludes that entry from the available set

### Requirement: Launch resolves crew type

The `launch` tool SHALL accept canonical `comp` and the legacy `composition` alias, resolve the effective value from the crew registry, and use that entry's image and directory when creating the crew. When both are supplied, `comp` is authoritative and a conflicting `composition` is ignored with a warning; if neither is supplied, the default SHALL be `"spec-ops"`.

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
- **THEN** the system uses `comp` (`"worker"`), resolves that entry, and logs a warning naming both values

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


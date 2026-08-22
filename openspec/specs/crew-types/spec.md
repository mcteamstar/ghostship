# crew-types Specification

## Purpose
Defines how crew types are declared, discovered, validated, and resolved at launch time — so different crews can have different compositions (agents, skills, steering, images) without code changes to the transport server.
## Requirements
### Requirement: Crew-type registry file
The system SHALL discover available crew types from a `crews/registry.json` file in the transport container, where each entry maps a type name to its configuration (image override, description, and the path to its directory under `crews/`).

#### Scenario: Registry lists available types
- **WHEN** the transport server starts and `crews/registry.json` exists
- **THEN** the system loads all crew type definitions from it and makes them available for launch and discovery

#### Scenario: Registry is missing
- **WHEN** `crews/registry.json` does not exist
- **THEN** the system falls back to a single implicit `"kirocrew"` type with the current hardcoded defaults (`KC_IMAGE`, `crews/kirocrew/manifest.json`, `crews/kirocrew/Containerfile`)

#### Scenario: Registry entry references a nonexistent directory
- **WHEN** a crew type entry in the registry points to a `crews/<type>/` directory that does not exist
- **THEN** the system logs a warning at startup and excludes that type from the available set rather than failing entirely

### Requirement: Crew-type definition schema
Each crew-type entry in `crews/registry.json` SHALL contain: `name` (string, kebab-case, 1-50 chars), `description` (string), `image` (optional string — container image override; defaults to `KC_IMAGE`), and `dir` (string — relative path under `crews/` containing the type's `manifest.json` and `Containerfile`).

#### Scenario: Minimal valid entry
- **WHEN** a registry entry specifies only `name`, `description`, and `dir`
- **THEN** the system uses the global `KC_IMAGE` default for that type's container image and resolves `manifest.json` from the specified `dir`

#### Scenario: Entry with image override
- **WHEN** a registry entry includes an `image` field
- **THEN** the system uses that image when launching crews of this type instead of the global `KC_IMAGE`

#### Scenario: Invalid name format
- **WHEN** a registry entry's `name` does not match `^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$` (or single char `^[a-z0-9]$`)
- **THEN** the system logs a warning and excludes that entry from the available set

### Requirement: Crew-type discovery tool
The system SHALL expose a `crew_types` MCP tool that returns the list of available crew types with their name and description.

#### Scenario: Listing crew types
- **WHEN** a caller invokes the `crew_types` tool with no arguments
- **THEN** the system returns an array of objects, each containing `name` and `description`, for every valid crew type in the registry

### Requirement: Launch resolves crew type
The `launch` tool SHALL accept an optional `crew_type` parameter (defaulting to `"kirocrew"`), resolve the matching registry entry, and use that entry's `image` and `dir` (for manifest lookup) when creating the crew container.

#### Scenario: Launch with default crew type
- **WHEN** `launch` is called without a `crew_type` argument
- **THEN** the system launches using the `"kirocrew"` type's configuration, preserving current behavior

#### Scenario: Launch with explicit crew type
- **WHEN** `launch` is called with `crew_type="worker"`
- **THEN** the system resolves the `"worker"` entry from the registry and uses its image and manifest path

#### Scenario: Launch with unknown crew type
- **WHEN** `launch` is called with a `crew_type` value not present in the loaded registry
- **THEN** the system returns an error naming the unknown type and listing available types

### Requirement: Crew type stored in registry entry
The system SHALL record the `crew_type` used at launch time in the crew's registry entry (`crews.json`), so downstream tools can inspect which type a running crew is.

#### Scenario: Registry entry includes crew type
- **WHEN** a crew is successfully launched with `crew_type="review"`
- **THEN** the crew's entry in `crews.json` includes `"crew_type": "review"`

#### Scenario: Existing crews without type field
- **WHEN** the system reads a crew registry entry that has no `crew_type` field (pre-migration)
- **THEN** it treats the crew as type `"kirocrew"` for display and operational purposes


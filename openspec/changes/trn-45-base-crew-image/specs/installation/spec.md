## MODIFIED Requirements

### Requirement: Container base images use deterministic references

All Containerfiles in the project SHALL pin base images to a specific version tag rather than floating tags. `transport/Containerfile` SHALL pin to a patch-version Python slim tag. `crews/_base/Containerfile` SHALL pin to a versioned KiroCrew semver tag and be the single source of that pin for the whole crew image stack. `crews/spec-ops/Containerfile` SHALL build `FROM localhost/base:latest`.

#### Scenario: Transport Containerfile pin
- **WHEN** `transport/Containerfile` is built
- **THEN** the `FROM` line references a patch-version-pinned Python slim image (e.g. `python:3.12.10-slim`)

#### Scenario: Base Containerfile versioned pin
- **WHEN** `crews/_base/Containerfile` is built
- **THEN** the `FROM` line references a semver-pinned KiroCrew image (e.g. `ghcr.io/kirodotdev/kirocrew:0.3.0`) and a comment documents the current version and update instructions

#### Scenario: spec-ops Containerfile builds on base
- **WHEN** `crews/spec-ops/Containerfile` is built
- **THEN** the `FROM` line references `localhost/base:latest` and the file adds only spec-ops-specific layers: Node.js, OpenSpec CLI, and the `org.ghostship.version` OCI label

### Requirement: NodeSource install includes integrity verification

The Node.js installation in `crews/spec-ops/Containerfile` SHALL NOT use an unverified curl-pipe-to-bash pattern. The install method SHALL verify the downloaded script's checksum before execution.

#### Scenario: Node.js install with integrity check
- **WHEN** `crews/spec-ops/Containerfile` installs Node.js via NodeSource
- **THEN** the setup script checksum is verified before piping to bash

## ADDED Requirements

### Requirement: Base crew image built before composition images

`install.sh` SHALL build `localhost/base:latest` from `crews/_base/Containerfile` before building any composition image. The `_base` directory is an internal build dependency and SHALL NOT appear as a composition in `crews/registry.json`.

#### Scenario: Fresh install builds base then spec-ops
- **WHEN** `install.sh` runs
- **THEN** it builds `localhost/base:latest` first, then builds `localhost/spec-ops:latest` from that base

#### Scenario: _base not exposed as a composition
- **WHEN** a client calls `crews()` or reads `transport://compositions`
- **THEN** `_base` does not appear as an available composition

### Requirement: Composition image version includes composition name

The `org.ghostship.version` OCI label on each composition image SHALL be `<VERSION>-<composition-name>` (e.g. `0.1.0-spec-ops`), where `VERSION` is the ghostship monorepo version passed as a build arg and the composition name matches the composition's directory name. This lets `crews()` identify both the ghostship release and which composition a crew was built from.

#### Scenario: spec-ops crew reports versioned label
- **WHEN** `crews()` is called and a spec-ops crew is registered
- **THEN** `crew_image_version` reads `"<VERSION>-spec-ops"` (e.g. `"0.1.0-spec-ops"`)

#### Scenario: Future composition follows same convention
- **WHEN** a new composition `research` is built with ghostship version `0.2.0`
- **THEN** its OCI label reads `"0.2.0-research"` and `crews()` reports that value

## ADDED Requirements

### Requirement: Container base images use deterministic references

All Containerfiles in the project SHALL pin base images to a specific patch version tag (e.g. `python:3.12.x-slim`) rather than floating minor/major tags. Where upstream does not publish stable versioned tags (e.g. `ghcr.io/kirodotdev/kirocrew:stable`), a comment SHALL document the floating-tag risk and the condition under which a pin becomes possible.

#### Scenario: Transport Containerfile pin

- **WHEN** `transport/Containerfile` is built
- **THEN** the `FROM` line references a patch-version-pinned Python slim image (e.g. `python:3.12.10-slim`)

#### Scenario: Crew Containerfile floating tag documentation

- **WHEN** `crews/spec-ops/Containerfile` references `ghcr.io/kirodotdev/kirocrew:stable`
- **THEN** a comment adjacent to the `FROM` line documents the floating-tag fragility and states the condition for pinning

### Requirement: NodeSource install includes integrity verification

The Node.js installation in `crews/spec-ops/Containerfile` SHALL NOT use an unverified curl-pipe-to-bash pattern. The install method SHALL either pin a specific NodeSource setup script version or verify the downloaded script's checksum before execution.

#### Scenario: Node.js install with integrity check

- **WHEN** the crew Containerfile installs Node.js via NodeSource
- **THEN** the install either pins a tagged release URL or verifies the setup script checksum before piping to bash

### Requirement: install.sh podman machine ssh error handling

All `podman machine ssh` invocations in `install.sh` SHALL have explicit error handling that aborts with a diagnostic message on failure.

#### Scenario: podman machine ssh failure

- **WHEN** a `podman machine ssh` command fails (non-zero exit)
- **THEN** `install.sh` prints a diagnostic message to stderr and exits with a non-zero status

### Requirement: install.sh readiness probe replaces fixed sleep

The health check in `install.sh` SHALL use a bounded retry probe against the transport's MCP endpoint rather than a fixed `sleep` delay.

#### Scenario: Transport becomes ready quickly

- **WHEN** the transport container starts and the MCP endpoint responds within the retry window
- **THEN** `install.sh` reports success immediately without waiting the full timeout

#### Scenario: Transport fails to become ready

- **WHEN** the transport container's MCP endpoint does not respond within the retry window
- **THEN** `install.sh` reports a health-check failure with diagnostic output

### Requirement: install.sh config source trust documentation

The `source "$CONFIG_FILE"` invocation in `install.sh` SHALL have an adjacent comment documenting that it executes arbitrary shell code from the user-supplied path and that this is an intentional trust assumption.

#### Scenario: Config file source comment present

- **WHEN** a developer reads the `source "$CONFIG_FILE"` line in `install.sh`
- **THEN** a comment immediately above or beside it explains the arbitrary-code-execution trust model

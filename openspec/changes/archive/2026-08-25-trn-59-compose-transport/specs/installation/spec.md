## NEW Requirements

### Requirement: Transport service definition generated as a Compose file
`install.sh` SHALL generate a `compose.yml` in `${DATA_DIR}` after building images, containing the complete `ga-transport` service definition: image, ports, volumes, environment variables, network, restart policy, and security options. The Podman socket path and all machine-specific values SHALL be baked in at generation time so the file is self-contained and usable without re-running `install.sh`.

`install.sh`, `start.sh`, and `uninstall.sh` SHALL all use `podman compose -f "${DATA_DIR}/compose.yml"` to manage the `ga-transport` container lifecycle, replacing raw `podman run`, `podman stop`, and `podman rm` calls.

#### Scenario: install.sh generates compose.yml
- **WHEN** `install.sh` completes the image build phase
- **THEN** `${DATA_DIR}/compose.yml` exists and contains a valid Compose service definition for `ga-transport` with all env vars, mounts, ports, and the host-specific Podman socket path

#### Scenario: start.sh starts a stopped transport
- **WHEN** `start.sh` is run and `ga-transport` is stopped or does not exist
- **THEN** `podman compose up -d` starts or recreates the container from `compose.yml` without requiring additional arguments

#### Scenario: start.sh is idempotent when transport is running
- **WHEN** `start.sh` is run and `ga-transport` is already running
- **THEN** `podman compose up -d` detects it is already up and makes no changes

#### Scenario: uninstall.sh tears down via compose
- **WHEN** `uninstall.sh` tears down `ga-transport`
- **THEN** `podman compose down` stops and removes the container cleanly

### Requirement: Podman >= 4.4 required
The system SHALL require Podman >= 4.4 so that `podman compose` is available as a built-in subcommand. `install.sh` SHALL check the Podman version and exit with a clear error if it is below 4.4.

#### Scenario: Podman version check passes
- **WHEN** `install.sh` runs and `podman --version` reports >= 4.4
- **THEN** installation proceeds normally

#### Scenario: Podman version check fails
- **WHEN** `install.sh` runs and `podman --version` reports < 4.4
- **THEN** the script exits with an error stating the minimum version requirement and how to upgrade

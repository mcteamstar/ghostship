## MODIFIED Requirements

### Requirement: Transport service definition generated as a Compose file
`install.sh` SHALL generate a `compose.yml` in `${DATA_DIR}` after building images, containing the complete `ga-transport` service definition: image, ports, volumes, environment variables, network, restart policy, and security options. The Podman socket path and all machine-specific values SHALL be baked in at generation time so the file is self-contained and usable without re-running `install.sh`.

`install.sh` SHALL copy the contents of `academy/` (subdirectories `agents`, `skills`, `steering`, `policies`, `orders`) and `crews/` from the ghostship repo into `${DATA_DIR}/academy/` and `${DATA_DIR}/crews/` respectively before writing `compose.yml`. These copies become the source of truth for the running transport container.

The six volume entries in the generated `compose.yml` that previously referenced the host repo path (`${GHOSTSHIP_DIR}/academy/*` and `${GHOSTSHIP_DIR}/crews`) SHALL instead reference the corresponding paths inside `${DATA_DIR}` (`${DATA_DIR}/academy/agents`, etc.). The transport container's internal mount points (`/agents`, `/skills`, `/steering`, `/policies`, `/orders`, `/crews`) SHALL remain unchanged.

`install.sh`, `start.sh`, and `uninstall.sh` SHALL all use `podman compose -f "${DATA_DIR}/compose.yml"` to manage the `ga-transport` container lifecycle, replacing raw `podman run`, `podman stop`, and `podman rm` calls.

#### Scenario: install.sh generates compose.yml
- **WHEN** `install.sh` completes the image build phase
- **THEN** `${DATA_DIR}/compose.yml` exists and contains a valid Compose service definition for `ga-transport` with all env vars, mounts, ports, and the host-specific Podman socket path

#### Scenario: install.sh copies academy and crews into data volume
- **WHEN** `install.sh` completes the image build phase
- **THEN** `${DATA_DIR}/academy/agents`, `${DATA_DIR}/academy/skills`, `${DATA_DIR}/academy/steering`, `${DATA_DIR}/academy/policies`, `${DATA_DIR}/academy/orders`, and `${DATA_DIR}/crews` all exist and contain the files from the corresponding repo directories

#### Scenario: install.sh generates compose.yml with data-volume mounts
- **WHEN** `install.sh` completes the image build phase
- **THEN** `${DATA_DIR}/compose.yml` contains volume entries sourced from `${DATA_DIR}/academy/*` and `${DATA_DIR}/crews` rather than the repo checkout path, while the container-internal mount points remain `/agents`, `/skills`, `/steering`, `/policies`, `/orders`, and `/crews`

#### Scenario: Transport container has no runtime dependency on repo path
- **WHEN** the ghostship repo is moved or deleted after `install.sh` has run
- **THEN** `start.sh` can still start the transport container successfully using `${DATA_DIR}/compose.yml`, because no mount in `compose.yml` references the old repo path

#### Scenario: Re-running install.sh refreshes the data-volume copies
- **WHEN** `install.sh` is run again after academy/ or crews/ files have been changed in the repo
- **THEN** the copies in `${DATA_DIR}/academy/` and `${DATA_DIR}/crews/` are replaced with the updated files and the transport container reflects those changes on next start

#### Scenario: start.sh starts a stopped transport
- **WHEN** `start.sh` is run and `ga-transport` is stopped or does not exist
- **THEN** `podman compose up -d` starts or recreates the container from `compose.yml` without requiring additional arguments

#### Scenario: start.sh is idempotent when transport is running
- **WHEN** `start.sh` is run and `ga-transport` is already running
- **THEN** `podman compose up -d` detects it is already up and makes no changes

#### Scenario: uninstall.sh tears down via compose
- **WHEN** `uninstall.sh` tears down `ga-transport`
- **THEN** `podman compose down` stops and removes the container cleanly

## ADDED Requirements

### Requirement: Documentation states that academy/ and crews/ changes require reinstall
`docs/configuration.md` and `README.md` SHALL include a note that `academy/` and `crews/` contents are snapshotted into the data volume at install time, and that changes to those directories require re-running `./install.sh` to take effect in a running transport.

#### Scenario: Developer edits an academy skill and expects it to take effect
- **WHEN** a developer edits a file under `academy/` in their repo checkout
- **THEN** they can consult `docs/configuration.md` or `README.md` and find that re-running `./install.sh` is required for the change to reach the transport container

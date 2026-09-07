## MODIFIED Requirements

### Requirement: podman-compose required as a prerequisite
The system SHALL require `podman-compose` to be installed before `install.sh` runs. `install.sh` SHALL check for `podman-compose` specifically and exit with a clear error and install instructions if it is not found. `docker-compose` and `docker compose` are NOT acceptable alternatives because Ghostship's generated `compose.yml` uses external Podman secrets that Docker Compose does not support.

`install.sh`, `start.sh`, and `uninstall.sh` SHALL set `PODMAN_COMPOSE_PROVIDER` to the resolved path of `podman-compose` before every `podman compose` invocation, so that Podman's provider-selection logic cannot pick Docker Compose when both are installed.

#### Scenario: compose provider present
- **WHEN** `install.sh` runs and `podman-compose` is on `PATH`
- **THEN** installation proceeds normally

#### Scenario: no compose provider found
- **WHEN** `install.sh` runs and `podman-compose` is not found
- **THEN** the script exits with an error and prints the install command for `podman-compose` on the detected OS

#### Scenario: Docker Compose present but podman-compose absent — still fails
- **WHEN** `install.sh` runs and `docker-compose` is installed but `podman-compose` is not
- **THEN** the script exits with an error (it does NOT proceed using Docker Compose)

#### Scenario: Both providers installed — podman-compose is used
- **WHEN** both `podman-compose` and `docker-compose` are installed
- **THEN** all `podman compose` invocations in `install.sh`, `start.sh`, and `uninstall.sh` use `podman-compose` as the provider, not Docker Compose

#### Scenario: uninstall.sh with podman-compose absent
- **WHEN** `uninstall.sh` runs and `podman-compose` has already been removed from the system
- **THEN** the script falls back to direct `podman rm` calls to remove `ga-transport` and `ga-portal`, rather than failing or using Docker Compose

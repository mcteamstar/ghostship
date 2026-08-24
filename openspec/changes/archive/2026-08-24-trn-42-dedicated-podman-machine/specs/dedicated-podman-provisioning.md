# Spec: Dedicated Podman Machine Provisioning

## Purpose

Provision and manage a dedicated Podman machine (macOS) or dedicated Podman instance (Linux) exclusively for Ghost Academy crew containers, isolated from the host's default Podman runtime.

## Requirements

### Requirement: Opt-in dedicated machine via config flag

The system SHALL provision a dedicated Podman machine/instance only when `GA_DEDICATED_MACHINE=true` is set. When unset or `false`, behaviour is unchanged.

#### Scenario: Dedicated machine disabled (default)
- **GIVEN** `GA_DEDICATED_MACHINE` is unset or `false`
- **WHEN** `install.sh` runs
- **THEN** the script uses the default Podman socket (existing behaviour)

#### Scenario: Dedicated machine enabled
- **GIVEN** `GA_DEDICATED_MACHINE=true`
- **WHEN** `install.sh` runs
- **THEN** the script provisions a dedicated Podman instance named by `GA_MACHINE_NAME` (default `ghostship`) and uses its socket for the transport

### Requirement: macOS dedicated machine lifecycle

On macOS, the system SHALL create and manage a dedicated `podman machine` VM separate from the default machine.

#### Scenario: First install with dedicated machine on macOS
- **GIVEN** `GA_DEDICATED_MACHINE=true` and OS is Darwin
- **WHEN** `install.sh` runs and no machine named `ghostship` exists
- **THEN** the script runs `podman machine init ghostship --cpus $GA_MACHINE_CPUS --memory $GA_MACHINE_MEMORY --disk-size $GA_MACHINE_DISK`
- **AND** starts the machine
- **AND** enables `podman-restart.service` inside the guest

#### Scenario: Subsequent install with existing dedicated machine on macOS
- **GIVEN** `GA_DEDICATED_MACHINE=true` and OS is Darwin and machine `ghostship` already exists
- **WHEN** `install.sh` runs
- **THEN** the script starts the machine if not running (no re-init)
- **AND** uses the existing machine's socket

#### Scenario: Dedicated machine resource configuration
- **GIVEN** `GA_DEDICATED_MACHINE=true` and OS is Darwin
- **WHEN** machine is initialised
- **THEN** CPUs are set to `GA_MACHINE_CPUS` (default 4), memory to `GA_MACHINE_MEMORY` (default 8192 MB), disk to `GA_MACHINE_DISK` (default 60 GB)

### Requirement: Linux dedicated Podman instance

On Linux, the system SHALL create a dedicated systemd socket-activated Podman service with its own storage root.

#### Scenario: First install with dedicated machine on Linux
- **GIVEN** `GA_DEDICATED_MACHINE=true` and OS is Linux
- **WHEN** `install.sh` runs and `podman-ghostship.socket` does not exist
- **THEN** the script writes `podman-ghostship.socket` and `podman-ghostship.service` unit files to `~/.config/systemd/user/`
- **AND** runs `systemctl --user daemon-reload`
- **AND** enables and starts `podman-ghostship.socket`

#### Scenario: Socket path on Linux
- **GIVEN** `GA_DEDICATED_MACHINE=true` and OS is Linux
- **WHEN** the dedicated instance is provisioned
- **THEN** the socket path is `/run/user/<UID>/podman/ghostship.sock`

#### Scenario: Storage isolation on Linux
- **GIVEN** `GA_DEDICATED_MACHINE=true` and OS is Linux
- **WHEN** the dedicated Podman service starts
- **THEN** it uses `--root ~/.local/share/ghostship/containers/storage` and `--runroot $XDG_RUNTIME_DIR/ghostship-containers`
- **AND** containers are invisible to the default `podman ps`

### Requirement: Transport binds to dedicated socket

The transport container SHALL mount and use the dedicated socket when `GA_DEDICATED_MACHINE=true`.

#### Scenario: Transport socket binding
- **GIVEN** `GA_DEDICATED_MACHINE=true`
- **WHEN** the transport container is started
- **THEN** the `-v` bind mount and `PODMAN_SOCKET` env var reference the dedicated socket path
- **AND** the transport can create, list, and remove containers via this socket

### Requirement: Dedicated machine uninstall

`uninstall.sh` SHALL remove the dedicated machine/instance when it was provisioned.

#### Scenario: Uninstall on macOS with dedicated machine
- **GIVEN** a dedicated machine `ghostship` exists
- **WHEN** `uninstall.sh` runs
- **THEN** the script stops the machine, removes all GA containers/volumes on it, and removes the machine

#### Scenario: Uninstall on Linux with dedicated instance
- **GIVEN** dedicated systemd units exist
- **WHEN** `uninstall.sh` runs
- **THEN** the script disables and removes the socket/service units, removes the dedicated storage root

### Requirement: Configurable machine name

The machine/instance name SHALL be configurable via `GA_MACHINE_NAME` (default `ghostship`).

#### Scenario: Custom machine name
- **GIVEN** `GA_DEDICATED_MACHINE=true` and `GA_MACHINE_NAME=academy`
- **WHEN** `install.sh` runs on macOS
- **THEN** the podman machine is named `academy` instead of `ghostship`

# Spec Delta

## MODIFIED Requirements

### Requirement: Idempotent, repeatable install

The system SHALL be safe to re-run: existing images are rebuilt, the existing ga-transport container is replaced, and already-existing ga-portside and ga-starboard networks are left untouched rather than erroring. Crew workspace/home volumes are out of scope for install.sh — they are created per-crew by launch, not by installation.

#### Scenario: Re-running install.sh
- **WHEN** install.sh is run again on a machine that already has Podman, ga-portside, ga-starboard, and a running ga-transport container
- **THEN** the script removes and recreates only the ga-transport container with freshly built images, without erroring on the existing networks

### Requirement: Dedicated Podman machine by default

install.sh SHALL provision a dedicated Podman machine (macOS) or dedicated systemd socket-activated Podman instance (Linux) exclusively for Ghost Academy unless GA_DEDICATED_MACHINE=false is explicitly set. This is the default because a dedicated machine/instance is exclusive to Ghost Academy — only ga-transport, ga-portside, ga-starboard, crew containers, and their images ever run on it — which isolates Ghost Academy from the host's default Podman runtime (avoiding contention or interference from IDE plugins or other tooling) with no ongoing cost beyond one-time provisioning.

The dedicated instance is controlled by GA_MACHINE_NAME (default ghost-academy), GA_MACHINE_CPUS (default 8), GA_MACHINE_MEMORY (default 8192 MB), and GA_MACHINE_DISK (default 100 GB). All three resource variables are ceilings, not upfront host reservations: GA_MACHINE_CPUS caps concurrent vCPU threads time-shared by the host scheduler (bounded by Apple's Virtualization.framework maximumAllowedCPUCount and physical cores minus one on macOS); GA_MACHINE_MEMORY is demand-paged host memory, so idle usage stays below the configured value; GA_MACHINE_DISK is backed by a sparse file, so blocks are consumed as data is written. All five variables SHALL be documented in docs/configuration.md and included as commented-out entries in config/ghostship.conf.example, with GA_DEDICATED_MACHINE=false shown as the opt-out value. None of the five has a command-line flag; they are config-file-only with no ambient-environment-variable fallback, per the config-file capability's resolution order.

#### Scenario: Default — dedicated machine
- **WHEN** GA_DEDICATED_MACHINE is unset
- **THEN** install.sh provisions or uses the dedicated machine/instance named by GA_MACHINE_NAME

#### Scenario: Opt-out — default Podman socket
- **WHEN** GA_DEDICATED_MACHINE=false
- **THEN** install.sh uses the default Podman socket

#### Scenario: macOS — first install with dedicated machine
- **WHEN** GA_DEDICATED_MACHINE is not false, the OS is macOS, and no machine named by GA_MACHINE_NAME exists
- **THEN** install.sh runs podman machine init with the configured CPU, memory, and disk limits, starts the machine, enables podman-restart.service in the guest, and uses that machine's in-guest socket for Transport

#### Scenario: macOS — subsequent install with existing dedicated machine
- **WHEN** GA_DEDICATED_MACHINE is not false, the OS is macOS, and the named machine already exists
- **THEN** install.sh starts it if not running, does not re-initialize it, and uses its socket

#### Scenario: Linux — first install with dedicated instance
- **WHEN** GA_DEDICATED_MACHINE is not false and the OS is Linux
- **THEN** install.sh writes podman-GA_MACHINE_NAME.socket and service units under the user's systemd directory, reloads systemd, enables and starts the socket, and uses the resulting runtime socket for Transport

#### Scenario: Linux — storage isolation
- **WHEN** GA_DEDICATED_MACHINE is not false and the OS is Linux
- **THEN** the dedicated Podman service uses a storage root under the GA_MACHINE_NAME data directory, separate from default Podman storage, so its containers are not shown by podman ps on the default instance

#### Scenario: Transport binds to dedicated socket
- **WHEN** GA_DEDICATED_MACHINE is not false
- **THEN** the Transport container receives the dedicated socket mount and PODMAN_SOCKET points to it

#### Scenario: Every Podman command targets the dedicated instance
- **WHEN** GA_DEDICATED_MACHINE is not false
- **THEN** image pulls, every podman build, network and secret creation, Transport startup, and failure-path logs all target the same resolved dedicated-instance connection and none falls back to the default Podman socket

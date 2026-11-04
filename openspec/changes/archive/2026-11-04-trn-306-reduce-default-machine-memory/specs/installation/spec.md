# Spec Delta

## MODIFIED Requirements

### Requirement: Dedicated Podman machine by default

`install.sh` SHALL provision a dedicated Podman machine (macOS) or dedicated systemd socket-activated Podman instance (Linux) exclusively for Ghost Academy unless `GA_DEDICATED_MACHINE=false` is explicitly set. This is the default because a dedicated machine/instance is exclusive to Ghost Academy — only `ga-transport`, `ga-net`, crew containers, and their images ever run on it — which isolates GA fully from the host's default Podman runtime (avoiding contention or interference from IDE plugins or other tooling) with no ongoing cost beyond the one-time VM/instance provisioning.

The dedicated instance is controlled by `GA_MACHINE_NAME` (default `ghost-academy`), `GA_MACHINE_CPUS` (default 8), `GA_MACHINE_MEMORY` (default 8192 MB), and `GA_MACHINE_DISK` (default 100 GB). All three resource variables are ceilings, not upfront host reservations: `GA_MACHINE_CPUS` caps concurrent vCPU threads that the host scheduler time-shares across real cores (bounded by Apple's Virtualization.framework `maximumAllowedCPUCount`, physical cores minus one, on macOS); `GA_MACHINE_MEMORY` is backed by demand-paged host memory (Apple's Virtualization.framework), so idle host usage stays far below the configured value; `GA_MACHINE_DISK` is backed by a sparse file, so actual disk blocks are only consumed as data is written. All five variables SHALL be documented in `docs/configuration.md` and included as commented-out entries in `config/ghostship.conf.example`, with the example's commented value showing how to opt out (`GA_DEDICATED_MACHINE=false`) rather than the (now-default) enabled value. None of the five has a corresponding command-line flag; they are config-file-only, per the `config-file` capability's resolution order (built-in default → config file → flag), with no ambient-environment-variable fallback.

#### Scenario: Default — dedicated machine
- **WHEN** `GA_DEDICATED_MACHINE` is unset
- **THEN** `install.sh` provisions/uses the dedicated machine/instance named `GA_MACHINE_NAME`

#### Scenario: Opt-out — default Podman socket
- **WHEN** `GA_DEDICATED_MACHINE=false`
- **THEN** `install.sh` uses the default Podman socket, unchanged from pre-dedicated-machine behaviour

#### Scenario: macOS — first install with dedicated machine
- **WHEN** `GA_DEDICATED_MACHINE` is not `false` and OS is macOS and no machine named `GA_MACHINE_NAME` exists
- **THEN** `install.sh` runs `podman machine init <name> --cpus <GA_MACHINE_CPUS> --memory <GA_MACHINE_MEMORY> --disk-size <GA_MACHINE_DISK>`, starts the machine, enables `podman-restart.service` inside the guest, and uses that machine's in-guest socket for the transport

#### Scenario: macOS — subsequent install with existing dedicated machine
- **WHEN** `GA_DEDICATED_MACHINE` is not `false` and OS is macOS and the named machine already exists
- **THEN** `install.sh` starts the machine if not running (no re-init) and uses its socket

#### Scenario: Linux — first install with dedicated instance
- **WHEN** `GA_DEDICATED_MACHINE` is not `false` and OS is Linux
- **THEN** `install.sh` writes `podman-<GA_MACHINE_NAME>.socket` and `podman-<GA_MACHINE_NAME>.service` systemd unit files under `~/.config/systemd/user/`, reloads the daemon, enables and starts the socket, and uses the resulting socket at `$XDG_RUNTIME_DIR/podman/<GA_MACHINE_NAME>.sock`

#### Scenario: Linux — storage isolation
- **WHEN** `GA_DEDICATED_MACHINE` is not `false` and OS is Linux
- **THEN** the dedicated Podman service uses `--root ~/.local/share/<GA_MACHINE_NAME>/containers/storage` so its containers are invisible to `podman ps` on the default instance

#### Scenario: Transport binds to dedicated socket
- **WHEN** `GA_DEDICATED_MACHINE` is not `false`
- **THEN** the transport container is started with the dedicated socket bind-mounted and `PODMAN_SOCKET` pointing to it

#### Scenario: Every Podman command targets the dedicated instance
- **WHEN** `GA_DEDICATED_MACHINE` is not `false`
- **THEN** the image pull, every `podman build`, the network create, the secret create, the transport `run`, and the failure-path `logs` tail SHALL all target the same resolved dedicated-instance connection — none SHALL fall back to the default Podman socket

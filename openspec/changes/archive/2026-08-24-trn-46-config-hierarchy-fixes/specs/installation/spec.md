## MODIFIED Requirements

### Requirement: Opt-in dedicated Podman machine

`install.sh` SHALL provision a dedicated Podman machine (macOS) or dedicated systemd socket-activated Podman instance (Linux) exclusively for Ghost Academy only when `GA_DEDICATED_MACHINE=true`. When unset or `false`, behaviour is unchanged — the default Podman socket is used.

The dedicated instance is controlled by `GA_MACHINE_NAME` (default `ghost-academy`), `GA_MACHINE_CPUS` (default 4), `GA_MACHINE_MEMORY` (default 8192 MB), and `GA_MACHINE_DISK` (default 60 GB). All five variables SHALL be documented in `docs/configuration.md` and included as commented-out entries in `config/ghostship.conf.example`. None of the five has a corresponding command-line flag; they are config-file-only, per the `config-file` capability's resolution order (built-in default → config file → flag), with no ambient-environment-variable fallback.

#### Scenario: Default — no dedicated machine
- **WHEN** `GA_DEDICATED_MACHINE` is unset or `false`
- **THEN** `install.sh` uses the default Podman socket, unchanged from existing behaviour

#### Scenario: macOS — first install with dedicated machine
- **WHEN** `GA_DEDICATED_MACHINE=true` and OS is macOS and no machine named `GA_MACHINE_NAME` exists
- **THEN** `install.sh` runs `podman machine init <name> --cpus <GA_MACHINE_CPUS> --memory <GA_MACHINE_MEMORY> --disk-size <GA_MACHINE_DISK>`, starts the machine, enables `podman-restart.service` inside the guest, and uses that machine's in-guest socket for the transport

#### Scenario: macOS — subsequent install with existing dedicated machine
- **WHEN** `GA_DEDICATED_MACHINE=true` and OS is macOS and the named machine already exists
- **THEN** `install.sh` starts the machine if not running (no re-init) and uses its socket

#### Scenario: Linux — first install with dedicated instance
- **WHEN** `GA_DEDICATED_MACHINE=true` and OS is Linux
- **THEN** `install.sh` writes `podman-<GA_MACHINE_NAME>.socket` and `podman-<GA_MACHINE_NAME>.service` systemd unit files under `~/.config/systemd/user/`, reloads the daemon, enables and starts the socket, and uses the resulting socket at `$XDG_RUNTIME_DIR/podman/<GA_MACHINE_NAME>.sock`

#### Scenario: Linux — storage isolation
- **WHEN** `GA_DEDICATED_MACHINE=true` and OS is Linux
- **THEN** the dedicated Podman service uses `--root ~/.local/share/<GA_MACHINE_NAME>/containers/storage` so its containers are invisible to `podman ps` on the default instance

#### Scenario: Transport binds to dedicated socket
- **WHEN** `GA_DEDICATED_MACHINE=true`
- **THEN** the transport container is started with the dedicated socket bind-mounted and `PODMAN_SOCKET` pointing to it

#### Scenario: Every Podman command targets the dedicated instance
- **WHEN** `GA_DEDICATED_MACHINE=true`
- **THEN** the image pull, every `podman build`, the network create, the secret create, the transport `run`, and the failure-path `logs` tail SHALL all target the same resolved dedicated-instance connection — none SHALL fall back to the default Podman socket

### Requirement: Dedicated machine uninstall

`uninstall.sh` SHALL remove the dedicated machine or instance when `GA_DEDICATED_MACHINE=true`. A `--keep-machine` flag SHALL preserve the machine/instance while still removing Ghost Academy containers and volumes. `uninstall.sh` SHALL accept the same `--config <path>` flag as `install.sh` and resolve `GA_MACHINE_NAME` (and `GA_DEDICATED_MACHINE`) using the identical built-in-default → config-file resolution order, with no ambient-environment-variable fallback — so a dedicated machine created under a name customised via config file is correctly found and torn down rather than left behind.

#### Scenario: Uninstall on macOS with dedicated machine
- **WHEN** `uninstall.sh` runs and `GA_DEDICATED_MACHINE=true` and OS is macOS
- **THEN** Ghost Academy containers and volumes are removed from the dedicated machine, and the machine is stopped and removed — unless `--keep-machine` is passed

#### Scenario: Uninstall on Linux with dedicated instance
- **WHEN** `uninstall.sh` runs and `GA_DEDICATED_MACHINE=true` and OS is Linux
- **THEN** the systemd socket and service units are disabled and removed, and the dedicated storage root is removed — unless `--keep-machine` is passed

#### Scenario: Uninstall finds a custom-named dedicated machine via config file
- **WHEN** `uninstall.sh --config ./my.conf` runs and `my.conf` exports `GA_MACHINE_NAME=academy`, and a dedicated machine named `academy` exists
- **THEN** `uninstall.sh` detects and removes the `academy` machine, not a machine named `ghost-academy`

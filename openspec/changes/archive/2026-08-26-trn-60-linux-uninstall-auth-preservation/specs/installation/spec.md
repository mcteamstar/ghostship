## MODIFIED Requirements

### Requirement: File-based transport auth persistence
The installation SHALL persist reusable kiro-cli auth as a single plain file, `DATA_DIR/ga-kiro-auth`, mode `0600` — not a Podman secret. No dedicated bind mount, migration step, or file-driver access is needed: `DATA_DIR` is already bind-mounted read/write into the transport container as `/data`, so transport reads and writes the file directly.

#### Scenario: Install with no existing auth file
- **WHEN** installation runs before `ga-kiro-auth` exists
- **THEN** the transport starts with no auth file present, and the existing first-time device-auth flow remains available to create it

#### Scenario: Install with an existing auth file
- **WHEN** installation runs and `DATA_DIR/ga-kiro-auth` already has content from a previous install
- **THEN** the transport reads it directly via the existing `/data` mount, with no separate migration or projection step required

#### Scenario: Ordinary uninstall preserves reusable auth
- **WHEN** uninstall runs without `--purge-auth`
- **THEN** transport state other than `ga-kiro-auth` is removed while that file is retained

#### Scenario: Ordinary uninstall on Linux preserves reusable auth even without --keep-machine
- **WHEN** `uninstall.sh` runs on Linux without `--purge-auth` and without `--keep-machine`
- **THEN** `ga-kiro-auth` is retained; only the dedicated instance's `containers/` storage root is removed during machine teardown, not the entire `~/.local/share/${GA_MACHINE_NAME}` tree

#### Scenario: Purge uninstall removes reusable auth
- **WHEN** uninstall runs with `--purge-auth`
- **THEN** `ga-kiro-auth` is also removed

### Requirement: Dedicated machine uninstall

`uninstall.sh` SHALL remove the dedicated machine or instance unless `GA_DEDICATED_MACHINE=false` is resolved (mirroring `install.sh`'s default-on behaviour). A `--keep-machine` flag SHALL preserve the machine/instance while still removing Ghost Academy containers and volumes. `uninstall.sh` SHALL accept the same `--config <path>` flag as `install.sh` and resolve `GA_MACHINE_NAME` (and `GA_DEDICATED_MACHINE`) using the identical built-in-default → config-file resolution order, with no ambient-environment-variable fallback — so a dedicated machine created under a name customised via config file is correctly found and torn down rather than left behind.

On Linux, the machine teardown SHALL remove only the dedicated `containers/` storage subdirectory, not the entire `~/.local/share/${GA_MACHINE_NAME}` tree. The `data/` subdirectory (which contains `ga-kiro-auth`) is handled separately by the data-dir cleanup step, which respects `--purge-auth`.

#### Scenario: Uninstall on macOS with dedicated machine
- **WHEN** `uninstall.sh` runs, `GA_DEDICATED_MACHINE` is not `false`, and OS is macOS
- **THEN** Ghost Academy containers and volumes are removed from the dedicated machine, and the machine is stopped and removed — unless `--keep-machine` is passed

#### Scenario: Uninstall on Linux with dedicated instance
- **WHEN** `uninstall.sh` runs, `GA_DEDICATED_MACHINE` is not `false`, and OS is Linux
- **THEN** the systemd socket and service units are disabled and removed, and the dedicated `containers/` storage subdirectory is removed — unless `--keep-machine` is passed — while `data/` is left to the data-dir cleanup step

#### Scenario: Linux machine teardown does not remove data directory
- **WHEN** `uninstall.sh` runs on Linux without `--keep-machine`
- **THEN** `~/.local/share/${GA_MACHINE_NAME}/containers` is removed but `~/.local/share/${GA_MACHINE_NAME}/data` is NOT removed by the machine teardown block

#### Scenario: Uninstall finds a custom-named dedicated machine via config file
- **WHEN** `uninstall.sh --config ./my.conf` runs and `my.conf` exports `GA_MACHINE_NAME=academy`, and a dedicated machine named `academy` exists
- **THEN** `uninstall.sh` detects and removes the `academy` machine, not a machine named `ghost-academy`

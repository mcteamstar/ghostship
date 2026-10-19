# Installation Specification

## Purpose

Install and run Ghost Academy locally on either macOS or Linux with a single script, handling the platform differences (podman-machine VM vs native Podman) transparently so the rest of the system never needs to know which OS it's on.

## Requirements

### Requirement: Cross-platform Podman provisioning
The system SHALL detect the host OS via `uname -s` and verify that `podman` and `podman-compose` are installed before proceeding. If either is missing, `install.sh` SHALL exit with a clear error and print the install command for the detected OS. Podman and podman-compose are prerequisites that must be installed before running `install.sh` — the script does not install them itself.

#### Scenario: Podman not installed
- **WHEN** `install.sh` runs and `podman` is not on `PATH`
- **THEN** the script exits with an error and prints the install command for the detected OS (e.g. `brew install podman` on macOS, `sudo apt-get install -y podman podman-compose` on Ubuntu)

#### Scenario: podman-compose not installed
- **WHEN** `install.sh` runs, `podman` is on `PATH`, but no compose provider (`podman-compose`, `docker-compose`, or `docker compose`) is found
- **THEN** the script exits with an error and prints the install command for podman-compose on the detected OS

#### Scenario: Unsupported platform
- **WHEN** `install.sh` runs on an OS that is neither Darwin nor Linux
- **THEN** the script exits with an error rather than guessing a package manager

### Requirement: Platform-appropriate Podman runtime setup
The system SHALL initialise and start a `podman machine` VM on macOS (since macOS has no container-capable kernel of its own), and SHALL use Podman directly on the host with no VM on Linux.

#### Scenario: macOS machine bootstrap
- **WHEN** `install.sh` runs on Darwin and no podman machine exists
- **THEN** the script initialises one (`--cpus 4 --memory 8192 --disk-size 60`), starts it, and enables `podman-restart.service` inside the guest

#### Scenario: Linux native socket
- **WHEN** `install.sh` runs on Linux
- **THEN** the script enables and starts `podman.socket` and `podman-restart.service` directly via `systemctl --user`, with no guest VM involved

### Requirement: Configurable port
The system SHALL accept a `--port` flag controlling the MCP listener port (default `64057`). MCP and file routes share a single port. The system SHALL also accept a `--public-url` flag to set the externally-visible base URL.

#### Scenario: Default port
- **WHEN** `install.sh` runs without `--port`
- **THEN** the transport container listens on `64057`

#### Scenario: Custom port
- **WHEN** `install.sh` runs with `--port 9000`
- **THEN** the transport container listens on `9000`

#### Scenario: Public URL flag
- **WHEN** `install.sh` runs with `--public-url https://academy.example.com`
- **THEN** the transport container's environment SHALL include `GA_HOST_URL=https://academy.example.com`

#### Scenario: Public URL flag omitted
- **WHEN** `install.sh` runs without `--public-url`
- **THEN** `GA_HOST_URL` defaults to `http://localhost:{PORT}`

### Requirement: Config file resolution
The system SHALL resolve configuration by deep-merging three layers in order: built-in
defaults, then `config/ghostship.yaml` in the ghostship directory (if present), then
the XDG override file (if present). When `--config <path>` is passed, it replaces
layers 2 and 3 entirely. The system SHALL resolve `KIRO_IDENTITY_PROVIDER`
and `KIRO_REGION` from the merged config under `backends.kiro.identity_center.*`
before falling back to individual CLI flags, then an interactive prompt if still
unset and running in a terminal.

#### Scenario: Repo config sets identity provider
- **WHEN** `config/ghostship.yaml` sets `backends.kiro.identity_provider` and `backends.kiro.region`
- **AND** no `--identity-provider` flag is passed
- **THEN** install.sh uses the config values

#### Scenario: XDG override sets identity provider
- **WHEN** the XDG override file sets `backends.kiro.identity_provider`
- **AND** `config/ghostship.yaml` does not set it
- **THEN** install.sh uses the XDG value

#### Scenario: --config flag replaces implicit resolution
- **WHEN** `--config /path/to/custom.yaml` is passed
- **THEN** only that file and built-in defaults are used; repo and XDG files are ignored

### Requirement: Auto-migration from ghostship.conf on install
When install.sh finds `config/ghostship.conf` with no `config/ghostship.yaml`, it
SHALL automatically convert the conf to YAML, write `config/ghostship.yaml`, rename
the old file to `config/ghostship.conf.bak`, and print a clear migration notice
before proceeding with the install.

#### Scenario: Auto-migration runs on upgrade
- **WHEN** `config/ghostship.conf` exists and `config/ghostship.yaml` does not
- **THEN** install.sh prints a migration notice, writes `config/ghostship.yaml`, and renames `config/ghostship.conf` to `config/ghostship.conf.bak`

#### Scenario: Install proceeds after migration
- **WHEN** auto-migration completes
- **THEN** install.sh continues with the migrated `config/ghostship.yaml` and completes normally

### Requirement: Wizard generates ghostship.yaml
The install wizard (run on first install or with `--wizard`) SHALL generate
`config/ghostship.yaml` with operator-supplied values and inline comments from an
internal template. It SHALL NOT generate `ghostship.conf`.

After the transport has passed its health check, the wizard SHALL unconditionally run `ghostship setup` to wire skill symlinks and register the MCP server for all detected agent clients. No confirmation prompt is shown for this step — the wizard always wires harnesses on a successful first install.

#### Scenario: Wizard writes YAML config
- **WHEN** the wizard completes
- **THEN** `config/ghostship.yaml` exists with the operator's choices and all other keys commented out at their defaults

#### Scenario: Wizard does not overwrite existing config
- **WHEN** `config/ghostship.yaml` already exists and `--wizard` is passed
- **THEN** the wizard prompts before overwriting (existing behaviour preserved)

#### Scenario: Wizard runs ghostship setup unconditionally
- **WHEN** the wizard completes and the transport passes its health check
- **THEN** `ghostship setup` is invoked automatically with no confirmation prompt, and skill symlinks and MCP registration are applied for all detected agent clients

#### Scenario: Wizard setup fails gracefully
- **WHEN** `ghostship setup` invoked by the wizard exits non-zero (e.g. no supported agent client detected)
- **THEN** a warning is printed but the overall install exits 0; `ghostship setup` can be re-run manually

### Requirement: Idempotent, repeatable install
The system SHALL be safe to re-run: existing images are rebuilt, the existing `ga-transport` container is replaced, and an already-existing `ga-net` network is left untouched rather than erroring. Crew workspace/home volumes are out of scope for `install.sh` — they are created per-crew by `launch`, not by installation.

#### Scenario: Re-running install.sh
- **WHEN** `install.sh` is run again on a machine that already has Podman, `ga-net`, and a running `ga-transport` container
- **THEN** the script removes and recreates only the `ga-transport` container with freshly built images, without erroring on the already-existing network

### Requirement: File-based transport auth persistence
The installation SHALL persist backend credentials only as plain files under `DATA_DIR`, mode `0600`, written by the transport's credential store. They SHALL NOT be stored as Podman secrets. No dedicated bind mount, migration step, or file-driver access is needed: `DATA_DIR` is already bind-mounted read/write into the transport container as `/data`, so the transport reads and writes the files directly.

#### Scenario: Install with no existing auth file
- **WHEN** installation runs before any backend credential exists
- **THEN** the transport starts with an empty credential store, and `ghostship auth login <backend>` remains available to populate it

#### Scenario: Install with an existing auth file
- **WHEN** installation runs and `DATA_DIR` already holds backend credentials from a previous install
- **THEN** the transport reads them directly via the existing `/data` mount, and the installer neither reads nor modifies them

#### Scenario: Ordinary uninstall preserves reusable auth
- **WHEN** uninstall runs without `--purge-auth`
- **THEN** transport state other than the backend credential files (kiro, claude and codex) is removed while those files are retained

#### Scenario: Ordinary uninstall on Linux preserves reusable auth even without --keep-machine
- **WHEN** `uninstall.sh` runs on Linux without `--purge-auth` and without `--keep-machine`
- **THEN** the backend credential files are retained; only the dedicated instance's `containers/` storage root is removed during machine teardown, not the entire `~/.local/share/${GA_MACHINE_NAME}` tree

#### Scenario: Purge uninstall removes reusable auth
- **WHEN** uninstall runs with `--purge-auth`
- **THEN** every backend credential file is also removed

#### Scenario: Uninstall removes obsolete credential secrets
- **WHEN** uninstall runs and obsolete backend credential Podman secrets (`ga-crew-anthropic-api-key`, `ga-claude-code-oauth-token`, `ga-crew-openai-api-key`, `ga-kiro-api-key`) exist
- **THEN** those secrets are removed

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

### Requirement: GA_API_KEY is delivered to the transport container via Podman secret
The installation SHALL create a Podman secret named `ga-api-key` (via `podman secret create`) containing the operator-supplied API key. The transport container SHALL receive the secret via `--secret ga-api-key` and read it from `/run/secrets/ga-api-key` at startup. The `-e GA_API_KEY=...` environment variable SHALL NOT be passed to the container.

When `--api-key` is not provided and no persisted key file exists, the secret SHALL NOT be created and the container SHALL start without `--secret ga-api-key` (authentication disabled).

#### Scenario: Fresh install with --api-key flag
- **WHEN** `install.sh` is run with `--api-key <value>`
- **THEN** `podman secret create ga-api-key` is invoked with the provided value, the transport container is started with `--secret ga-api-key`, and `/run/secrets/ga-api-key` inside the container contains the key

#### Scenario: Re-install with persisted key
- **WHEN** `install.sh` is run without `--api-key` but a persisted key file exists in DATA_DIR
- **THEN** the existing `ga-api-key` Podman secret is removed and recreated from the persisted file, and the container uses the refreshed secret

#### Scenario: Install without API key
- **WHEN** `install.sh` is run without `--api-key` and no persisted key file exists
- **THEN** no Podman secret is created, the container starts without `--secret`, and MCP API-key authentication is disabled

#### Scenario: API key not visible via podman inspect or /proc
- **WHEN** the transport container is running with `--secret ga-api-key`
- **THEN** `podman inspect ga-transport` does not show the API key in `Config.Env` or any other field, and `/proc/1/environ` inside the container does not contain `GA_API_KEY`

### Requirement: Transport reads GA_API_KEY from the secrets filesystem
The transport server process SHALL read the API key from `/run/secrets/ga-api-key` at startup. If the file does not exist or is empty, the transport SHALL behave as if no API key was configured (authentication disabled). The `GA_API_KEY` environment variable SHALL be treated as a deprecated fallback: if the file is absent but the env var is set, the transport SHALL use the env var and log a deprecation warning.

#### Scenario: Secret file present
- **WHEN** the transport starts and `/run/secrets/ga-api-key` exists with non-empty content
- **THEN** the transport uses its content (stripped of leading/trailing whitespace) as the bearer token for authentication

#### Scenario: Secret file absent, env var set (deprecated fallback)
- **WHEN** the transport starts and `/run/secrets/ga-api-key` does not exist but `GA_API_KEY` env var is set
- **THEN** the transport uses the env var value and logs a deprecation warning at startup

#### Scenario: Neither secret file nor env var
- **WHEN** the transport starts and neither `/run/secrets/ga-api-key` nor `GA_API_KEY` env var is available
- **THEN** API-key authentication is disabled and the transport logs an info message

### Requirement: Dedicated Podman machine by default

`install.sh` SHALL provision a dedicated Podman machine (macOS) or dedicated systemd socket-activated Podman instance (Linux) exclusively for Ghost Academy unless `GA_DEDICATED_MACHINE=false` is explicitly set. This is the default because a dedicated machine/instance is exclusive to Ghost Academy — only `ga-transport`, `ga-net`, crew containers, and their images ever run on it — which isolates GA fully from the host's default Podman runtime (avoiding contention or interference from IDE plugins or other tooling) with no ongoing cost beyond the one-time VM/instance provisioning.

The dedicated instance is controlled by `GA_MACHINE_NAME` (default `ghost-academy`), `GA_MACHINE_CPUS` (default 8), `GA_MACHINE_MEMORY` (default 16384 MB), and `GA_MACHINE_DISK` (default 100 GB). All three resource variables are ceilings, not upfront host reservations: `GA_MACHINE_CPUS` caps concurrent vCPU threads that the host scheduler time-shares across real cores (bounded by Apple's Virtualization.framework `maximumAllowedCPUCount`, physical cores minus one, on macOS); `GA_MACHINE_MEMORY` is backed by demand-paged host memory (Apple's Virtualization.framework), so idle host usage stays far below the configured value; `GA_MACHINE_DISK` is backed by a sparse file, so actual disk blocks are only consumed as data is written. All five variables SHALL be documented in `docs/configuration.md` and included as commented-out entries in `config/ghostship.conf.example`, with the example's commented value showing how to opt out (`GA_DEDICATED_MACHINE=false`) rather than the (now-default) enabled value. None of the five has a corresponding command-line flag; they are config-file-only, per the `config-file` capability's resolution order (built-in default → config file → flag), with no ambient-environment-variable fallback.

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

### Requirement: Transport service definition generated as a Compose file
`install.sh` SHALL generate a `compose.yml` in `${DATA_DIR}` after building images, containing the complete `ga-transport` service definition: image, ports, volumes, environment variables, network, restart policy, and security options. The Podman socket path and all machine-specific values SHALL be baked in at generation time so the file is self-contained and usable without re-running `install.sh`.

`install.sh` SHALL copy the contents of `academy/` (subdirectories `agents`, `skills`, `steering`, `policies`, `orders`, `mcp`) and `crews/` from the ghostship repo into `${DATA_DIR}/academy/` and `${DATA_DIR}/crews/` respectively before writing `compose.yml`. These copies become the source of truth for the running transport container.

The seven volume entries in the generated `compose.yml` SHALL include `${DATA_DIR}/academy/mcp:/mcp:ro` alongside the existing academy and crews entries. The transport container's internal mount point for the catalogue SHALL be `/mcp`. The transport container's internal mount points (`/agents`, `/skills`, `/steering`, `/policies`, `/orders`, `/crews`) SHALL remain unchanged.

`install.sh`, `start.sh`, and `uninstall.sh` SHALL all use `podman compose -f "${DATA_DIR}/compose.yml"` to manage the `ga-transport` container lifecycle, replacing raw `podman run`, `podman stop`, and `podman rm` calls.

#### Scenario: install.sh generates compose.yml
- **WHEN** `install.sh` completes the image build phase
- **THEN** `${DATA_DIR}/compose.yml` exists and contains a valid Compose service definition for `ga-transport` with all env vars, mounts, ports, and the host-specific Podman socket path

#### Scenario: install.sh copies academy and crews into data volume
- **WHEN** `install.sh` completes the image build phase
- **THEN** `${DATA_DIR}/academy/agents`, `${DATA_DIR}/academy/skills`, `${DATA_DIR}/academy/steering`, `${DATA_DIR}/academy/policies`, `${DATA_DIR}/academy/orders`, `${DATA_DIR}/academy/mcp`, and `${DATA_DIR}/crews` all exist and contain the files from the corresponding repo directories

#### Scenario: install.sh copies academy/mcp into data volume
- **WHEN** `install.sh` completes the image build phase and `academy/mcp/` exists in the repo
- **THEN** `${DATA_DIR}/academy/mcp/` exists and contains the files from `academy/mcp/`

#### Scenario: install.sh generates compose.yml with data-volume mounts
- **WHEN** `install.sh` completes the image build phase
- **THEN** `${DATA_DIR}/compose.yml` contains volume entries sourced from `${DATA_DIR}/academy/*` and `${DATA_DIR}/crews` rather than the repo checkout path, while the container-internal mount points remain `/agents`, `/skills`, `/steering`, `/policies`, `/orders`, `/mcp`, and `/crews`

#### Scenario: install.sh generates compose.yml with /mcp mount
- **WHEN** `install.sh` completes the image build phase
- **THEN** `${DATA_DIR}/compose.yml` contains a volume entry `${DATA_DIR}/academy/mcp:/mcp:ro`

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

### Requirement: Shell scripts reorganised under scripts/
`start.sh` and `uninstall.sh` SHALL be located at `bin/start.sh` and `bin/uninstall.sh` respectively. `install.sh` at the repo root SHALL remain as a shim that delegates to `bin/install.sh` with all arguments forwarded, preserving backward compatibility for existing workflows. The shim SHALL forward `--client-only` and all other flags unchanged.

#### Scenario: start.sh and uninstall.sh in scripts/
- **WHEN** a user clones the repository
- **THEN** `bin/start.sh` and `bin/uninstall.sh` exist and are executable, and no `start.sh` or `uninstall.sh` exist at the repo root

#### Scenario: install.sh shim at root
- **WHEN** `./install.sh [flags]` is invoked
- **THEN** `bin/install.sh [flags]` runs with all arguments forwarded and the exit code is preserved

#### Scenario: install.sh shim forwards --client-only
- **WHEN** `./install.sh --client-only [flags]` is invoked
- **THEN** `bin/install.sh --client-only [flags]` runs with all arguments forwarded and the exit code is preserved

### Requirement: PyYAML vendored — python3 is the only YAML config prerequisite

The ghostship repository SHALL include a vendored copy of the PyYAML pure-Python
package at `bin/lib/vendor/yaml/`. `bin/install.sh`, `bin/start.sh`, and
`bin/uninstall.sh` SHALL invoke `yaml_config.py` with
`PYTHONPATH="${GHOSTSHIP_DIR}/bin/lib/vendor" python3` so that `import yaml`
always resolves to the vendored copy without requiring PyYAML to be installed
on the system Python, and without creating a virtual environment. The only
prerequisite for YAML config parsing SHALL be a working `python3` binary.

#### Scenario: Install succeeds with only python3 — no PyYAML installed
- **WHEN** `bin/install.sh --client-only` is invoked on a host where PyYAML is not installed in the system Python
- **THEN** the install completes successfully, no venv is created, and no pip or uv commands are executed

#### Scenario: Vendored yaml takes precedence over any system installation
- **WHEN** `bin/install.sh` invokes `yaml_config.py`
- **THEN** the `yaml` module resolves from `bin/lib/vendor/` via `PYTHONPATH`, regardless of whether a different version is installed system-wide

### Requirement: ghostship CLI available on PATH after install
`bin/install.sh` SHALL make the `ghostship` CLI script available on `PATH` after a successful run.

#### Scenario: ~/.local/bin present and on PATH
- **WHEN** `bin/install.sh` completes successfully and `~/.local/bin` exists and is on `PATH`
- **THEN** `~/.local/bin/ghostship` is a symlink pointing to the `ghostship` script in the repo

#### Scenario: ~/.local/bin not on PATH
- **WHEN** `bin/install.sh` completes and `~/.local/bin` is not on `PATH`
- **THEN** `bin/install.sh` prints a clear one-line message instructing the user to add `~/.local/bin` to their `PATH`

### Requirement: podman-compose required as a prerequisite
The system SHALL require `podman-compose` to be installed before `install.sh` runs. `install.sh` SHALL check for `podman-compose` specifically and exit with a clear error and install instructions if it is not found. `docker-compose` and `docker compose` are NOT acceptable alternatives because Ghostship's generated `compose.yml` uses external Podman secrets that Docker Compose does not support.

`install.sh`, `start.sh`, and `uninstall.sh` SHALL set `PODMAN_COMPOSE_PROVIDER` to the resolved path of `podman-compose` before every `podman compose` invocation, so that Podman's provider-selection logic cannot pick Docker Compose when both are installed.

`install.sh` SHALL inject `GA_PORTAL_SESSION_TTL_SECS` into the generated `compose.yml` transport environment block, so that the session TTL configured in `ghostship.conf` takes effect at runtime.

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

#### Scenario: GA_PORTAL_SESSION_TTL_SECS is injected into compose.yml
- **WHEN** `GA_PORTAL_SESSION_TTL_SECS` is set in `ghostship.conf` and `install.sh` runs
- **THEN** the generated `compose.yml` contains `GA_PORTAL_SESSION_TTL_SECS=<value>` in the transport container environment

### Requirement: Documentation states that academy/ and crews/ changes require reinstall
`docs/configuration.md` and `README.md` SHALL include a note that `academy/` and `crews/` contents are snapshotted into the data volume at install time, and that changes to those directories require re-running `./install.sh` to take effect in a running transport.

#### Scenario: Developer edits an academy skill and expects it to take effect
- **WHEN** a developer edits a file under `academy/` in their repo checkout
- **THEN** they can consult `docs/configuration.md` or `README.md` and find that re-running `./install.sh` is required for the change to reach the transport container

### Requirement: Rate limiting env vars documented in configuration docs

`docs/configuration.md` SHALL include a "Rate Limiting" section that documents all six
`GA_RATE_LIMIT_*` environment variables introduced by TRN-52: their names, the
`<count>:<window_secs>` format, the default value for each, and the behaviour on
parse failure. The section SHALL note that rate limiter state is held in memory and
resets on process restart.

#### Scenario: Operator consults docs to tune /mcp rate limit
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they find a table or list of all `GA_RATE_LIMIT_*` variables with their
  defaults and format, and can set `GA_RATE_LIMIT_MCP=600:120` with confidence

### Requirement: Rate limiting env vars included in example config

`config/ghostship.conf.example` SHALL include commented-out entries for all six
`GA_RATE_LIMIT_*` variables, each showing its default value in `<count>:<window_secs>`
format (or `true`/`false` for the master switch). Comments SHALL explain the format.

#### Scenario: Operator copies example config to customise limits
- **WHEN** an operator copies `config/ghostship.conf.example` to customise their
  installation
- **THEN** the `GA_RATE_LIMIT_*` entries are present, commented out, and show the
  correct default values

### Requirement: spec-ops image conditionally includes Claude Code toolchain

The spec-ops image SHALL include `claude-agent-acp` (npm package) and the `claude` CLI when `claude` is a member of the enabled backend set. They SHALL be installed by the toolchain script `crews/spec-ops/toolchains/claude.sh`, which the image build runs only when `claude` appears in the `AGENT_TOOLCHAINS` build arg. The toolchain SHALL NOT be installed by default, to keep the baseline image lean.

The installed versions SHALL be pinned (exact version tags, not floating) in the Claude toolchain script.

#### Scenario: Default image build does not include Claude toolchain
- **WHEN** `install.sh` runs and `GA_AGENT_BACKENDS` does not list `claude`
- **THEN** the built spec-ops image does not contain `claude-agent-acp` or `claude` CLI

#### Scenario: Claude-enabled image build
- **WHEN** the spec-ops image is built with `AGENT_TOOLCHAINS` containing `claude`
- **THEN** the resulting image contains `claude-agent-acp` (pinned npm package) and the `claude` CLI binary at a known, pinned version

#### Scenario: Pinned versions in Containerfile
- **WHEN** `crews/spec-ops/toolchains/claude.sh` is read
- **THEN** its install steps reference exact version tags, not `latest` or floating ranges

### Requirement: spec-ops image conditionally includes Codex toolchain

The spec-ops image SHALL include the `codex-acp` adapter (npm package `@agentclientprotocol/codex-acp`) when `codex` is a member of the enabled backend set. It SHALL be installed by the toolchain script `crews/spec-ops/toolchains/codex.sh`, which the image build runs only when `codex` appears in the `AGENT_TOOLCHAINS` build arg. This is ONE component, not two: the adapter ships its own compatible Codex binary, so no separate `codex` CLI is installed. The toolchain SHALL NOT be installed by default, to keep the baseline image lean.

The installed version SHALL be pinned (an exact version tag, not a floating range) in the Codex toolchain script.

#### Scenario: Default image build does not include Codex toolchain
- **WHEN** `install.sh` runs and `GA_AGENT_BACKENDS` does not list `codex`
- **THEN** the built spec-ops image does not contain the `codex-acp` adapter

#### Scenario: Codex-enabled image build
- **WHEN** the spec-ops image is built with `AGENT_TOOLCHAINS` containing `codex`
- **THEN** the resulting image contains the `codex-acp` adapter (pinned npm package) resolvable on the crew's PATH

#### Scenario: Pinned version in Containerfile
- **WHEN** `crews/spec-ops/toolchains/codex.sh` is read
- **THEN** its install step references an exact version tag, not `latest` or a floating range

### Requirement: KiroCrew 0.7.x crew config options

The crew config patch applied by the transport SHALL use `sandbox_allow_unsandboxed_exec: true` instead of `sandbox: "off"` for Podman rootless compatibility. It SHALL set `orchestrator.max_plan_duration_seconds` to a value above 7200 to accommodate long SDD runs. The Captain check-in cron SHALL include `minimal_context: true` to reduce token cost on low-overhead Raven patrols.

#### Scenario: sandbox_allow_unsandboxed_exec set in crew config

- **WHEN** the transport applies the crew config patch via `_patch_crew_config`
- **THEN** `config.local.json` inside the crew contains `agent.sandbox_allow_unsandboxed_exec = true` and does NOT contain `agent.sandbox = "off"`

#### Scenario: orchestrator.max_plan_duration_seconds set above 7200

- **WHEN** the transport applies the crew config patch
- **THEN** `config.local.json` inside the crew contains `orchestrator.max_plan_duration_seconds >= 14400` so that multi-persona SDD orchestration sessions are not cut off by the 0.7.0 default 2h limit

#### Scenario: Raven patrol cron uses minimal_context

- **WHEN** the transport creates the Captain check-in (Raven patrol) cron via the `/api/crons` endpoint
- **THEN** the cron body includes `minimal_context: true`, reducing per-wake token cost from ~55k to ~200 tokens

### Requirement: GA_AGENT_BACKENDS drives toolchain inclusion at install time

`install.sh` SHALL pass one build arg, `AGENT_TOOLCHAINS`, to the spec-ops image build: the normalised members of `GA_AGENT_BACKENDS` other than kiro, comma-separated. Each listed name SHALL match `^[a-z][a-z0-9-]*$` and be `kiro` or the basename of a script in `crews/spec-ops/toolchains/`; otherwise `install.sh` SHALL exit before building. Enabling an available backend SHALL need only a config change and an install run.

#### Scenario: Set enables the Claude toolchain
- **WHEN** `GA_AGENT_BACKENDS=claude` is set in `ghostship.conf` and `install.sh` runs
- **THEN** the spec-ops image build receives `--build-arg AGENT_TOOLCHAINS=claude`

#### Scenario: Set enables several toolchains
- **WHEN** `GA_AGENT_BACKENDS=claude,codex` is set and `install.sh` runs
- **THEN** the image build receives `--build-arg AGENT_TOOLCHAINS=claude,codex`

#### Scenario: Kiro-only set builds no optional toolchain
- **WHEN** `GA_AGENT_BACKENDS` is unset and `install.sh` runs
- **THEN** the image build receives `--build-arg AGENT_TOOLCHAINS=` (empty) and no toolchain script runs

#### Scenario: Name without a toolchain script is rejected
- **WHEN** `GA_AGENT_BACKENDS=opencode` is set and `install.sh` runs
- **THEN** `install.sh` exits non-zero before building, naming `opencode` and the available toolchains

#### Scenario: Path-like name is rejected
- **WHEN** `GA_AGENT_BACKENDS=../toolchains/claude` is set and `install.sh` runs
- **THEN** `install.sh` exits non-zero before building, and no script outside `crews/spec-ops/toolchains/` is referenced

### Requirement: Toolchains are defined per backend, not hard-coded in the build

Each optional backend's toolchain SHALL be one script under `crews/spec-ops/toolchains/`, named after the backend. The image build SHALL run the scripts named in `AGENT_TOOLCHAINS` and no others, and SHALL fail if any script fails. The Containerfile SHALL NOT contain per-backend install logic. Adding a new backend's toolchain SHALL NOT change the Containerfile, `install.sh`, or other toolchain scripts.

#### Scenario: Adding a toolchain leaves the build unchanged
- **WHEN** a new backend script is added under `crews/spec-ops/toolchains/`
- **THEN** the Containerfile, `install.sh`, and the Claude and Codex scripts are byte-identical to their previous versions

#### Scenario: Unlisted toolchain contributes nothing
- **WHEN** a backend is not named in `AGENT_TOOLCHAINS`
- **THEN** its script does not run and the image contains none of that toolchain

#### Scenario: A failing toolchain fails the build
- **WHEN** a listed toolchain script exits non-zero
- **THEN** the image build fails and names the failing script

### Requirement: The transport receives the enabled set

`install.sh` SHALL write `GA_AGENT_BACKENDS` into the transport container's environment as the normalised list it used for `AGENT_TOOLCHAINS`: lowercase, comma-separated in first-listed order, without duplicates, without kiro, and empty when only kiro is enabled. It SHALL NOT write `GA_INCLUDE_CLAUDE_AGENT` or `GA_INCLUDE_CODEX_AGENT` into that environment.

#### Scenario: Compose environment carries the set
- **WHEN** `GA_AGENT_BACKENDS=claude` is set and `install.sh` generates the compose file
- **THEN** the transport service environment contains `GA_AGENT_BACKENDS=claude` and contains neither retired variable

#### Scenario: Compose value is normalised
- **WHEN** `GA_AGENT_BACKENDS=" Kiro, CODEX,,claude,codex"` is set and `install.sh` generates the compose file
- **THEN** the transport service environment contains `GA_AGENT_BACKENDS=codex,claude`

#### Scenario: Kiro-only compose value is empty
- **WHEN** `GA_AGENT_BACKENDS` is unset and `install.sh` generates the compose file
- **THEN** the transport service environment contains `GA_AGENT_BACKENDS=` (empty)

### Requirement: Config documentation covers GA_AGENT_BACKENDS

`docs/configuration.md` and `config/ghostship.conf.example` SHALL document `GA_AGENT_BACKENDS`, `GA_CREW_ACP_BACKEND`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `OPENAI_API_KEY` and `OPENAI_BASE_URL`, each with its default, valid values and dependencies, and SHALL NOT document the retired `GA_INCLUDE_*` variables except as removed.

#### Scenario: Config docs cover the consolidated variable
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they find `GA_AGENT_BACKENDS`, `GA_CREW_ACP_BACKEND` and the four `ANTHROPIC_*` and `OPENAI_*` settings documented, each with its default, valid values and which backend it belongs to

### Requirement: install.sh checks the default backend before building

`install.sh` SHALL exit with an error before building any image when `GA_CREW_ACP_BACKEND` is set to a value that is neither `kiro` nor a member of `GA_AGENT_BACKENDS`. The message SHALL name both settings. This catches a configuration the transport would reject at startup, before a full build and a restart loop.

#### Scenario: Default outside the set fails before the build
- **WHEN** `GA_CREW_ACP_BACKEND=codex` and `GA_AGENT_BACKENDS=claude` are set and `install.sh` runs
- **THEN** `install.sh` exits non-zero naming `GA_CREW_ACP_BACKEND` and `GA_AGENT_BACKENDS`, and no image is built

### Requirement: Changing the toolchain list forces a rebuild

The spec-ops image SHALL record its toolchain list in the `org.ghostship.toolchains` label, set from `AGENT_TOOLCHAINS`. When the existing image's label differs from the list `install.sh` is about to build, `install.sh` SHALL build the spec-ops image without the layer cache, so a stale toolchain layer is never reused.

#### Scenario: Adding a toolchain rebuilds without cache
- **WHEN** the existing spec-ops image has `org.ghostship.toolchains=claude` and `install.sh` runs with `GA_AGENT_BACKENDS=claude,codex`
- **THEN** the spec-ops image is built without the layer cache and its label becomes `claude,codex`

#### Scenario: Unchanged list keeps the cache
- **WHEN** the existing image's label equals the new `AGENT_TOOLCHAINS` value and the version is unchanged
- **THEN** `install.sh` does not force a cache-less spec-ops build on account of the toolchains

### Requirement: install.sh retries compose up on transient port conflict
`install.sh` SHALL retry the `podman compose up` invocation up to `GA_COMPOSE_RETRY_ATTEMPTS` times (default 3, minimum 1) with a `GA_COMPOSE_RETRY_DELAY_SECS`-second sleep (default 2) between attempts before giving up. On final failure, `install.sh` SHALL print the compose error output and exit non-zero.

#### Scenario: Compose up succeeds on first attempt
- **WHEN** `podman compose up` succeeds immediately
- **THEN** `install.sh` proceeds normally without sleeping

#### Scenario: Compose up fails transiently then succeeds
- **WHEN** `podman compose up` fails on the first attempt (e.g. transient port conflict) then succeeds on the second
- **THEN** `install.sh` sleeps `GA_COMPOSE_RETRY_DELAY_SECS` seconds and retries, and installation succeeds

#### Scenario: Compose up exhausts all retries
- **WHEN** `podman compose up` fails on every attempt up to `GA_COMPOSE_RETRY_ATTEMPTS`
- **THEN** `install.sh` prints the compose error to stderr and exits non-zero

#### Scenario: GA_COMPOSE_RETRY_ATTEMPTS=1 disables retry
- **WHEN** `GA_COMPOSE_RETRY_ATTEMPTS=1` is set and `podman compose up` fails
- **THEN** `install.sh` makes exactly one attempt, prints the error, and exits non-zero without sleeping

### Requirement: GA_COMPOSE_RETRY_ATTEMPTS and GA_COMPOSE_RETRY_DELAY_SECS documented
`docs/configuration.md` and `config/ghostship.conf.example` SHALL document `GA_COMPOSE_RETRY_ATTEMPTS` and `GA_COMPOSE_RETRY_DELAY_SECS` with their defaults, valid ranges, and purpose.

#### Scenario: Operator reads docs to disable retries
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they find `GA_COMPOSE_RETRY_ATTEMPTS` documented with its default (3) and that setting it to 1 disables retry

#### Scenario: Example config includes retry variables
- **WHEN** an operator opens `config/ghostship.conf.example`
- **THEN** `GA_COMPOSE_RETRY_ATTEMPTS` and `GA_COMPOSE_RETRY_DELAY_SECS` are present as commented-out entries with their default values

### Requirement: Nine internal vars hardcoded as constants

The following environment variables SHALL be removed from `Config.from_env()` and from
the `compose.yml` template. Their values SHALL be hardcoded as Python literals or
module-level constants:

| Variable | Hardcoded value |
|----------|----------------|
| `GA_CREW_AGENT` (KiroCrew internal agent name) | `"kiro"` constant |
| `TRANSPORT_DATA_DIR` | `"/data"` literal |
| `GA_ENABLE_SECURITY_HEADERS` | always `True` |
| `GA_TLS_MIN_VERSION` | `"1.2"` constant |
| `GA_PREWARM_ENABLED` | removed; prewarm always runs when triggered |
| `GA_PREWARM_TTL_SECS` | `300` module-level constant |
| `GA_SUBAGENT_MAX_TURNS` | `200` module-level constant |
| `GA_COMPOSE_RETRY_ATTEMPTS` | `3` constant in install.sh |
| `GA_COMPOSE_RETRY_DELAY_SECS` | `2` constant in install.sh |

#### Scenario: Removed vars have no effect when set in environment
- **WHEN** any of the nine removed vars is set in the environment or `ghostship.conf`
- **THEN** the transport ignores it and uses the hardcoded value; install.sh does not
  pass it through to compose

### Requirement: GA_CREW_AGENT replaces GA_CREW_ACP_BACKEND and GA_AGENT_BACKENDS

`GA_CREW_AGENT` SHALL be the single variable controlling which ACP backend is built into
the crew image and used at runtime. It replaces both `GA_CREW_ACP_BACKEND` (runtime
default) and `GA_AGENT_BACKENDS` (build-time list).

Valid values: `kiro` (default), `claude`, `codex`, `opencode`. A comma-separated list
(e.g. `GA_CREW_AGENT=claude,codex`) builds multiple toolchains; the first entry is the
runtime default.

`install.sh` SHALL derive `AGENT_TOOLCHAINS` (the set of toolchain scripts to install
into the crew image) from `GA_CREW_AGENT`. `GA_CREW_ACP_BACKEND` and `GA_AGENT_BACKENDS`
SHALL be accepted as deprecated aliases for one release cycle, with a printed warning
directing operators to use `GA_CREW_AGENT` instead.

#### Scenario: GA_CREW_AGENT=claude builds and runs Claude backend
- **WHEN** `GA_CREW_AGENT=claude` is set in `ghostship.conf` and `install.sh` runs
- **THEN** the crew image is built with the `claude.sh` toolchain
- **AND** the transport environment contains `GA_CREW_AGENT=claude`
- **AND** new crew containers use the Claude ACP backend by default

#### Scenario: Deprecated GA_CREW_ACP_BACKEND maps to GA_CREW_AGENT
- **WHEN** `GA_CREW_ACP_BACKEND=claude` is set and `GA_CREW_AGENT` is unset
- **THEN** install.sh prints a deprecation warning and treats `GA_CREW_AGENT=claude`
  for this run

#### Scenario: Deprecated GA_AGENT_BACKENDS maps to GA_CREW_AGENT
- **WHEN** `GA_AGENT_BACKENDS=claude,codex` is set and `GA_CREW_AGENT` is unset
- **THEN** install.sh prints a deprecation warning and treats `GA_CREW_AGENT=claude,codex`
  for this run

### Requirement: compose.yml adds volume mounts for host-path vars when set

When an operator-configurable variable contains a host filesystem path that the transport
reads at runtime, `install.sh` SHALL add a corresponding volume mount to the `ga-transport`
service so the path is reachable inside the container.

**GA_ORDERS_DIR:** When `GA_ORDERS_DIR` is non-empty, `install.sh` SHALL:
1. Require it to be an absolute path (error and abort if relative).
2. Warn (but continue) if the directory does not exist.
3. Add a read-only volume mount `<host_path>:/mnt/orders` to the compose `ga-transport` volumes.
4. Write `GA_ORDERS_DIR: "/mnt/orders"` (the fixed container path) into the compose environment block.

**GA_TLS_CERTFILE / GA_TLS_KEYFILE:** When both are non-empty, `install.sh` SHALL:
1. Error and abort if only one is set.
2. Error and abort if they do not share the same parent directory (same-directory requirement).
3. Add a read-only volume mount `<shared_parent_dir>:/mnt/tls` to the compose `ga-transport` volumes.
4. Write `GA_TLS_CERTFILE: "/mnt/tls/<cert_basename>"` and `GA_TLS_KEYFILE: "/mnt/tls/<key_basename>"` into the compose environment block.

#### Scenario: GA_ORDERS_DIR produces a volume mount and rewritten path
- **WHEN** `GA_ORDERS_DIR=/home/user/my-orders` is set and `install.sh` regenerates `compose.yml`
- **THEN** `compose.yml` contains `- /home/user/my-orders:/mnt/orders:ro` in the `ga-transport` volumes
- **AND** the transport environment contains `GA_ORDERS_DIR=/mnt/orders`

#### Scenario: GA_ORDERS_DIR relative path aborts install
- **WHEN** `GA_ORDERS_DIR=relative/path` is set and `install.sh` runs
- **THEN** `install.sh` exits non-zero with an error explaining an absolute path is required

#### Scenario: GA_ORDERS_DIR missing directory warns but continues
- **WHEN** `GA_ORDERS_DIR=/nonexistent/path` is set and `install.sh` runs
- **THEN** `install.sh` prints a warning that the directory does not exist but continues

#### Scenario: GA_TLS_CERTFILE and GA_TLS_KEYFILE produce a shared mount
- **WHEN** `GA_TLS_CERTFILE=/etc/tls/server.crt` and `GA_TLS_KEYFILE=/etc/tls/server.key` are set
- **THEN** `compose.yml` contains `- /etc/tls:/mnt/tls:ro` in the `ga-transport` volumes
- **AND** the transport environment contains `GA_TLS_CERTFILE=/mnt/tls/server.crt` and `GA_TLS_KEYFILE=/mnt/tls/server.key`

#### Scenario: Only one TLS var set aborts install
- **WHEN** `GA_TLS_CERTFILE=/etc/tls/server.crt` is set but `GA_TLS_KEYFILE` is unset
- **THEN** `install.sh` exits non-zero with an error stating both must be set together

#### Scenario: TLS cert and key in different directories aborts install
- **WHEN** `GA_TLS_CERTFILE=/etc/tls/cert.pem` and `GA_TLS_KEYFILE=/etc/pki/key.pem` are set
- **THEN** `install.sh` exits non-zero with an error explaining the same-directory requirement

### Requirement: PORT controls only the Caddy host port; transport internal port is fixed

The transport container SHALL always listen on port `64057` internally. `PORT` controls
the host port that Caddy (`ga-portal`) binds on. The compose `environment:` block for
`ga-transport` SHALL hard-code `PORT: "64057"` regardless of the operator-configured
`PORT` value. Caddy's upstream dial strings shall reference `ga-transport:64057`
unconditionally.

`docs/configuration.md` SHALL clarify this decoupling in the `PORT` entry.

#### Scenario: Custom PORT does not change transport internal port
- **WHEN** `PORT=9000` is set in `ghostship.conf` and `install.sh` regenerates `compose.yml`
- **THEN** Caddy binds on host port `9000`
- **AND** the transport container's `PORT` env var remains `64057`
- **AND** Caddy's upstream dial string remains `ga-transport:64057`

### Requirement: Model backend settings use their standard names

`install.sh` SHALL read the non-secret model backend settings under the names the Claude and Codex CLIs use: `ANTHROPIC_BASE_URL` and `OPENAI_BASE_URL`. Each SHALL be reset to empty before `ghostship.conf` is sourced, so a value exported in the invoking shell is never used.

#### Scenario: Standard names configure the backends
- **WHEN** `ghostship.conf` sets `ANTHROPIC_BASE_URL` and `OPENAI_BASE_URL`
- **THEN** `install.sh` passes them to the transport and prints no deprecation warning

#### Scenario: Shell values ignored
- **WHEN** `OPENAI_BASE_URL` is exported in the shell running `install.sh` and not set in `ghostship.conf`
- **THEN** the transport receives no `OPENAI_BASE_URL`

### Requirement: Pre-TRN-226 model backend names accepted as deprecated aliases

`install.sh` SHALL accept `GA_CREW_ANTHROPIC_BASE_URL` and `GA_CREW_OPENAI_BASE_URL` from `ghostship.conf` as aliases for the standard names. Each alias in use SHALL print a warning naming the old and new setting, never the value. When both names are set, the standard name SHALL win.

#### Scenario: Old name mapped with a warning
- **WHEN** `ghostship.conf` sets only `GA_CREW_OPENAI_BASE_URL`
- **THEN** `install.sh` uses its value as `OPENAI_BASE_URL` and warns that `GA_CREW_OPENAI_BASE_URL` is deprecated

#### Scenario: Standard name wins
- **WHEN** `ghostship.conf` sets both `OPENAI_BASE_URL` and `GA_CREW_OPENAI_BASE_URL`
- **THEN** `install.sh` uses `OPENAI_BASE_URL` and warns that the old name is ignored

### Requirement: Interactive guided setup when no ghostship.conf exists
When `install.sh` is run and no `ghostship.conf` exists in the current directory (or `--setup` flag is passed), the installer SHALL enter an interactive guided setup mode. The existing non-interactive path SHALL be unchanged when a `ghostship.conf` is present.

#### Scenario: Interactive mode triggered on first install
- **WHEN** `install.sh` is run and no `ghostship.conf` is found
- **THEN** the installer enters interactive guided setup and prompts the operator for configuration before building

#### Scenario: Non-interactive path unchanged when conf exists
- **WHEN** `install.sh` is run and a `ghostship.conf` exists
- **THEN** the installer proceeds non-interactively as before, without any prompts

### Requirement: Interactive setup collects backend and non-secret config
The interactive setup SHALL prompt the operator to choose a default agent backend (`kiro` default, `claude`, `codex`) and optional additional backends, then collect only the non-secret config for the selected backends (`KIRO_IDENTITY_PROVIDER`/`KIRO_REGION` for kiro; nothing for claude; `OPENAI_BASE_URL` for codex). Collected values SHALL be written to a new `ghostship.conf` (mode `600`, non-empty vars only, no secrets) before the build proceeds. All credentials SHALL be left to `ghostship auth login <backend>`.

#### Scenario: Selecting kiro backend prompts for identity provider
- **WHEN** the operator selects `kiro` as the backend
- **THEN** the installer prompts for `KIRO_IDENTITY_PROVIDER` and (when a provider is given) `KIRO_REGION` and writes them to `ghostship.conf`

#### Scenario: Selecting claude backend collects no secret config
- **WHEN** the operator selects `claude` as a backend
- **THEN** the installer collects no config and does not print a `ghostship auth login anthropic` hint (the post-start login offer covers it)

#### Scenario: Multiple backends enabled simultaneously
- **WHEN** the operator selects `kiro` as default and adds `claude,codex`
- **THEN** `GA_CREW_AGENT=kiro,claude,codex` is written to `ghostship.conf` with `kiro` as the runtime default

### Requirement: Interactive setup runs login flow after transport starts
After the transport starts successfully, the interactive setup SHALL offer, for each enabled backend with no stored credential, to run `ghostship auth login <backend>`. Accepting SHALL run that command in the foreground against the just-installed transport (including its port and bearer key). Declining SHALL print the command to run later. The install SHALL succeed either way.

#### Scenario: Login flow triggered automatically after install
- **WHEN** interactive setup starts the transport with `GA_CREW_AGENT=kiro,claude` and neither backend holds a credential
- **THEN** the operator is offered `ghostship auth login kiro` and then `ghostship auth login claude`

#### Scenario: Login on a keyed install
- **WHEN** the transport was installed with a bearer key and the operator accepts the login offer
- **THEN** the login request carries that key and succeeds

#### Scenario: Backend already authenticated
- **WHEN** a backend already holds a stored credential
- **THEN** no login is offered for it

### Requirement: Interactive setup offers harness registration
After login completes, the interactive setup SHALL offer to run `ghostship setup` to register the MCP server with detected harnesses (kiro-cli, Claude Code, opencode). The operator can accept or skip.

#### Scenario: Harness registration is optional
- **WHEN** the operator declines harness registration during interactive setup
- **THEN** the install completes normally without running `ghostship setup`

### Requirement: Installer never handles backend credentials
`install.sh` SHALL NOT read, create, remove or mount any backend credential: no `ga-crew-anthropic-api-key`, `ga-claude-code-oauth-token`, `ga-crew-openai-api-key` or `ga-kiro-api-key` secret operations, and no such secrets in the generated `compose.yml`. Re-running install, with or without `--wizard`, SHALL leave stored credentials unchanged.

#### Scenario: Re-install keeps credentials
- **WHEN** claude holds a stored setup-token and `install.sh --wizard` is run
- **THEN** claude's stored credential is unchanged after install

#### Scenario: Compose has no credential secrets
- **WHEN** `install.sh` generates `compose.yml`
- **THEN** it references none of the backend credential secrets

### Requirement: Credential settings in ghostship.conf are ignored with a warning
When `ghostship.conf` sets `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `OPENAI_API_KEY`, `KIRO_API_KEY`, `GA_CREW_ANTHROPIC_API_KEY` or `GA_CREW_OPENAI_API_KEY`, `install.sh` SHALL warn naming the setting and the `ghostship auth login <backend>` command that replaces it, never the value, and SHALL otherwise ignore it.

#### Scenario: Leftover token in conf
- **WHEN** `ghostship.conf` sets `CLAUDE_CODE_OAUTH_TOKEN`
- **THEN** install warns that it is ignored and to use `ghostship auth login claude`, and creates no secret

### Requirement: HOST controls only the Caddy host bind address

`HOST` (`network.host`) SHALL set only the host address `ga-portal` publishes on, for both `PORT` and the dashboard port range. It SHALL default to `127.0.0.1`. The transport container SHALL always listen on `0.0.0.0` internally, whatever `HOST` is, and Caddy's upstream dial strings SHALL remain `ga-transport:64057`. `docs/configuration.md` SHALL describe this split in the `HOST` entry.

#### Scenario: Default install is reachable only from the local machine
- **WHEN** `install.sh` regenerates `compose.yml` with `HOST` unset
- **THEN** `ga-portal` publishes `PORT` and the dashboard port range on `127.0.0.1` only
- **AND** the transport container listens on `0.0.0.0` inside its container

#### Scenario: Loopback HOST still reaches the transport through the portal
- **WHEN** `HOST=127.0.0.1` and a client on the host requests `http://localhost:{PORT}/mcp`
- **THEN** Caddy proxies the request to `ga-transport:64057` and the transport answers it, with no `502` from a refused upstream connection

#### Scenario: Custom HOST changes only the portal bind
- **WHEN** `HOST=192.168.1.10` is set and `install.sh` regenerates `compose.yml`
- **THEN** `ga-portal` publishes `PORT` and the dashboard port range on `192.168.1.10`
- **AND** the transport container's listen address remains `0.0.0.0`
- **AND** Caddy's upstream dial string remains `ga-transport:64057`

#### Scenario: Wildcard HOST exposes the portal on all interfaces
- **WHEN** `HOST=0.0.0.0` is set and `install.sh` regenerates `compose.yml`
- **THEN** `ga-portal` publishes `PORT` and the dashboard port range on all host interfaces

### Requirement: Install readiness is verified through the portal

`install.sh` and `ghostship start` SHALL report the transport ready only when a `/health` request sent to the address and `PORT` that `ga-portal` publishes on succeeds, and is proxied through to the transport. A transport that answers only inside its own container SHALL NOT count as ready. Wildcard `HOST` values SHALL be probed via `127.0.0.1`.

#### Scenario: Unreachable transport behind the portal fails readiness
- **WHEN** the transport is running but `ga-portal` cannot reach it, so `/health` through the portal returns `502`
- **THEN** `install.sh` does not report the transport ready and exits non-zero once the readiness timeout expires, naming the portal-to-transport path

#### Scenario: Specific HOST is probed at that address
- **WHEN** `HOST=192.168.1.10`
- **THEN** the readiness probe targets `http://192.168.1.10:{PORT}/health`

### Requirement: API key resolution order

`install.sh` SHALL resolve the endpoint API key from, in order of precedence: the `--api-key` flag, then `network.api_key` in the resolved YAML config, then the key persisted in `DATA_DIR` by a previous `--api-key`. A key or opt-out set in the YAML config SHALL NOT be overridden by a previously persisted key.

#### Scenario: YAML key wins over a stale persisted key
- **WHEN** `DATA_DIR/ga-api-key` holds `old-key`, `network.api_key` is `new-key`, and `install.sh` runs without `--api-key`
- **THEN** the transport is configured with `new-key`

#### Scenario: YAML opt-out wins over a persisted key
- **WHEN** `DATA_DIR/ga-api-key` holds a key, `network.api_key` is `false`, and `install.sh` runs without `--api-key`
- **THEN** API-key authentication is disabled

#### Scenario: Flag wins over YAML
- **WHEN** `network.api_key` is `yaml-key` and `install.sh` runs with `--api-key flag-key`
- **THEN** the transport is configured with `flag-key`

#### Scenario: Empty flag clears the persisted key and falls through to YAML
- **WHEN** `DATA_DIR` holds a persisted key, `network.api_key` is `yaml-key`, and `install.sh` runs with `--api-key ""`
- **THEN** the persisted key is deleted and the transport is configured with `yaml-key`

#### Scenario: Persisted key used when nothing else is set
- **WHEN** `DATA_DIR/ga-api-key` holds `old-key`, `network.api_key` is unset, and `install.sh` runs without `--api-key`
- **THEN** the transport is configured with `old-key`

### Requirement: Non-loopback installs require an API key or an explicit opt-out
The check SHALL evaluate the address `ga-portal` publishes on (`HOST`), never the transport's in-container listen address. A loopback `HOST` (unset, `127.0.0.0/8`, `::1`, `localhost`) needs no key. Any other `HOST` (`0.0.0.0`, `::`, or a specific address) SHALL need a non-empty key or the explicit opt-out `network.api_key: false`. If the key is unset, the install SHALL abort before starting any containers.

#### Scenario: Remote install without API key aborts
- **WHEN** `install.sh` is run with `HOST=0.0.0.0` and the API key is unset
- **THEN** `install.sh` aborts with a non-zero exit code before starting any containers

#### Scenario: Specific non-loopback address without API key aborts
- **WHEN** `install.sh` is run with `HOST=192.168.1.10` and the API key is unset
- **THEN** the install aborts with a non-zero exit code before starting any containers

#### Scenario: Local install without API key succeeds
- **WHEN** `install.sh` is run with `HOST=127.0.0.1` (or `HOST` unset) and the API key is unset
- **THEN** the install completes normally with no API-key warning, the portal is published on loopback only, and the transport starts without authentication

#### Scenario: Remote install with explicit opt-out succeeds
- **WHEN** `install.sh` is run with `HOST=0.0.0.0` and `network.api_key: false`
- **THEN** the install completes and the transport starts without authentication

#### Scenario: API key set on non-loopback address succeeds
- **WHEN** `install.sh` runs with `--api-key <value>` and `HOST=0.0.0.0`
- **THEN** the install completes with authentication enabled and no unauthenticated-access warning is printed

### Requirement: Unauthenticated non-loopback exposure is warned about
When an install aborts for an unset key, `install.sh` SHALL print a `WARNING` naming the published address and port, stating MCP endpoints would be reachable by any host that can reach it, and listing the fixes: set an API key, set `HOST=127.0.0.1`, or set `network.api_key: false`. With the opt-out on a non-loopback `HOST`, `install.sh` and the transport at startup SHALL each emit a `WARNING` that the endpoint is unauthenticated.

#### Scenario: Abort message lists the resolution paths
- **WHEN** `install.sh` aborts because `HOST=0.0.0.0` and the API key is unset
- **THEN** the WARNING names the address and port, and lists setting an API key, `HOST=127.0.0.1`, and `network.api_key: false`

#### Scenario: Opt-out install warns
- **WHEN** `install.sh` is run with `HOST=0.0.0.0` and `network.api_key: false`
- **THEN** `install.sh` prints a WARNING that the endpoint is unauthenticated by explicit choice

#### Scenario: Transport logs startup warning when unauthenticated on non-loopback
- **WHEN** the transport process starts with no API key, the explicit opt-out set, and a non-loopback portal address
- **THEN** the transport logs a `WARNING`-level message stating that no API key
  is configured and MCP endpoints are accessible without authentication

### Requirement: Transport startup enforces the API-key requirement
The transport SHALL re-check the API-key requirement at startup against the portal's published address, not its own in-container listen address. If the portal's published address is non-loopback, no API key secret is present, and the explicit opt-out is not set, the transport SHALL refuse to start and exit with a non-zero code.

#### Scenario: Transport refuses to start unauthenticated on non-loopback
- **WHEN** the transport starts with a non-loopback portal address, no `ga-api-key` secret, and no explicit opt-out
- **THEN** the transport exits immediately with a logged error naming the missing API key

#### Scenario: Fixed wildcard listen address does not trip the check
- **WHEN** the transport starts listening on `0.0.0.0` in its container, the portal's published address is `127.0.0.1`, and no API key is present
- **THEN** the transport starts normally without the API-key error

### Requirement: API-key opt-out and GA_TRUSTED_PROXY documented in configuration docs
`docs/configuration.md` SHALL document `network.api_key` (string to enable,
unset to require one on non-loopback installs, `false` to opt out explicitly)
and the deprecation of `network.require_api_key`/`GA_REQUIRE_API_KEY`, together
with `GA_TRUSTED_PROXY` (what it does, the default, and how to set it for
Caddy-fronted installs).

`config/ghostship.yaml.example` SHALL show `network.api_key` with a comment
describing all three states, and SHALL NOT include `network.require_api_key`.

#### Scenario: Operator reads docs to understand authentication posture options
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they find `network.api_key` documented with its three states and
  the abort behaviour, a deprecation note for `network.require_api_key`, and
  `GA_TRUSTED_PROXY` documented with its effect on rate-limit source-IP
  extraction

#### Scenario: Example config shows the opt-out
- **WHEN** an operator opens `config/ghostship.yaml.example`
- **THEN** `network.api_key` is present with a comment explaining string, unset,
  and `false`, and `network.require_api_key` is absent

## Interactive Setup Mode

### Trigger

Interactive guided setup runs when **either**:
- no `ghostship.conf` is found (neither `ghostship.conf` nor `config/ghostship.conf`) **and** stdin is a tty (`-t 0`); or
- the `--wizard` flag is passed (regardless of whether a config exists).

Otherwise the installer runs the existing non-interactive path unchanged.

### The seven steps

1. **Default backend** — prompt for `kiro`/`claude`/`codex` (default `kiro`); validate against the known set and re-prompt on an unknown value.
2. **Additional backends** — prompt for a comma-separated list (blank = none); validate each and append to `GA_CREW_AGENT` so all selected backends are enabled.
3. **Non-secret config per backend** — kiro: optional `KIRO_IDENTITY_PROVIDER` and, if set, `KIRO_REGION`; claude: none (printed note to run `ghostship auth login anthropic`); codex: optional `OPENAI_BASE_URL` (blank = OpenAI; may point at a local proxy such as litellm) plus a printed note to run `ghostship auth login openai`.
4. **Write `ghostship.conf`** — `${GHOSTSHIP_DIR}/config/ghostship.conf`, mode `600`, containing only the non-empty non-secret vars and a generation header. This file is sourced by the auto-detect loop on every subsequent `./install.sh`.
5. **Build & start** — the collected `GA_CREW_AGENT` feeds the existing `agent_backends_normalise` call and the normal build/transport-start path, unchanged.
6. **Authentication** — after `✓ Transport is ready`, kiro triggers `ghostship auth login` (device flow); claude and codex print the follow-up `ghostship auth login <backend>` command.
7. **Harness registration** — prompt (default `y`) to run `ghostship setup`, registering the MCP server with detected harnesses (kiro-cli, Claude Code, opencode). Declining skips it; the install still completes.

### Multi-backend topology

`GA_CREW_AGENT` is comma-separated and the transport holds config for all listed backends simultaneously (e.g. `GA_CREW_AGENT=kiro,claude,codex`). The **first** entry is the runtime default. The interactive installer surfaces this: a default backend plus any additional backends are enabled in one install.

### Invariants

- The non-interactive path (config present, no `--wizard`) is **unchanged** — no new prompts, no behavior change.
- No secrets are collected or written during interactive setup. Secret injection is deferred to `ghostship auth login <backend>`.

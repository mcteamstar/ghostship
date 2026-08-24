# Installation Specification

## Purpose

Install and run Ghost Academy locally on either macOS or Linux with a single script, handling the platform differences (podman-machine VM vs native Podman) transparently so the rest of the system never needs to know which OS it's on.

## Requirements

### Requirement: Cross-platform Podman provisioning
The system SHALL detect the host OS via `uname -s` and install Podman with the appropriate package manager if it is missing: Homebrew on Darwin, and on Linux whichever of `apt-get` or `dnf` is available.

#### Scenario: macOS without Podman
- **WHEN** `install.sh` runs on Darwin and `podman` is not on `PATH`
- **THEN** the script requires Homebrew and installs Podman via `brew install podman`

#### Scenario: Linux with apt
- **WHEN** `install.sh` runs on Linux, `podman` is not on `PATH`, and `apt-get` is available
- **THEN** the script installs Podman via `apt-get install podman`

#### Scenario: Linux with dnf
- **WHEN** `install.sh` runs on Linux, `podman` is not on `PATH`, `apt-get` is unavailable, and `dnf` is available
- **THEN** the script installs Podman via `dnf install podman`

#### Scenario: Unsupported platform
- **WHEN** `install.sh` runs on an OS that is neither Darwin nor Linux, or on Linux with neither `apt-get` nor `dnf` available
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
The system SHALL accept a `--port` flag controlling the MCP listener port (default `64057`), and SHALL always run the file server on `port + 1`. The system SHALL also accept `--file-public-url` and `--mcp-public-url` flags to set the externally-visible base URLs for the file server and MCP endpoint respectively.

#### Scenario: Default port
- **WHEN** `install.sh` runs without `--port`
- **THEN** the transport container listens on `64057` (MCP) and `64058` (files), matching `server.py`'s own defaults

#### Scenario: Custom port
- **WHEN** `install.sh` runs with `--port 9000`
- **THEN** the transport container listens on `9000` (MCP) and `9001` (files), and `GA_HOST_URL` is set to `http://localhost:9001`

#### Scenario: File public URL flag
- **WHEN** `install.sh` runs with `--file-public-url https://example.com/files`
- **THEN** the transport container's environment SHALL include `GA_FILE_PUBLIC_URL=https://example.com/files`

#### Scenario: MCP public URL flag
- **WHEN** `install.sh` runs with `--mcp-public-url https://example.com/mcp`
- **THEN** the transport container's environment SHALL include `GA_MCP_PUBLIC_URL=https://example.com/mcp`

#### Scenario: Both public URL flags together
- **WHEN** `install.sh` runs with `--file-public-url https://proxy.example.com/files --mcp-public-url https://proxy.example.com/mcp`
- **THEN** the transport container's environment SHALL include both `GA_FILE_PUBLIC_URL=https://proxy.example.com/files` and `GA_MCP_PUBLIC_URL=https://proxy.example.com/mcp`

#### Scenario: Public URL flags omitted
- **WHEN** `install.sh` runs without `--file-public-url` or `--mcp-public-url`
- **THEN** the transport container's environment SHALL NOT set `GA_FILE_PUBLIC_URL` or `GA_MCP_PUBLIC_URL`, leaving the transport to use its internal fallback logic

### Requirement: Identity provider configuration resolution order
The system SHALL resolve `KIRO_IDENTITY_PROVIDER`/`KIRO_REGION`/`KIRO_LICENSE` in a fixed order: a `--config` file first, then individual CLI flags, then an interactive prompt if still unset and running in a terminal.

#### Scenario: Config file sets identity provider, no flags override
- **WHEN** `install.sh` runs with `--config <path>` and the config file exports `KIRO_IDENTITY_PROVIDER` and no `--identity-provider` flag is passed
- **THEN** the transport uses the config file value

#### Scenario: CLI flag overrides config file identity provider
- **WHEN** `install.sh` runs with `--config <path> --identity-provider <url>` and the config file also exports `KIRO_IDENTITY_PROVIDER`
- **THEN** the CLI flag value wins (flags override config file)

#### Scenario: No config and non-interactive
- **WHEN** `install.sh` runs with none of `--config`, `--identity-provider` set, and stdin is not a terminal
- **THEN** the script proceeds without prompting, leaving identity provider settings unset (Builder ID fallback)

### Requirement: Config file integration with install flags
The `--config <path>` flag SHALL source the specified file before processing other flags. All flags in the argument parser (including `--file-public-url`, `--mcp-public-url`, `--port`, `--api-key`, etc.) SHALL override values set by the config file.

#### Scenario: Config file sets public URLs, flags override one
- **WHEN** `install.sh` runs with `--config ./proxy.conf --file-public-url https://override.com` and `proxy.conf` exports `GA_FILE_PUBLIC_URL=https://config.com` and `GA_MCP_PUBLIC_URL=https://config.com/mcp`
- **THEN** `GA_FILE_PUBLIC_URL` SHALL be `https://override.com` (flag wins) and `GA_MCP_PUBLIC_URL` SHALL be `https://config.com/mcp` (config default)

### Requirement: Idempotent, repeatable install
The system SHALL be safe to re-run: existing images are rebuilt, the existing `ga-transport` container is replaced, and an already-existing `ga-net` network is left untouched rather than erroring. Crew workspace/home volumes are out of scope for `install.sh` — they are created per-crew by `launch`, not by installation.

#### Scenario: Re-running install.sh
- **WHEN** `install.sh` is run again on a machine that already has Podman, `ga-net`, and a running `ga-transport` container
- **THEN** the script removes and recreates only the `ga-transport` container with freshly built images, without erroring on the already-existing network

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

#### Scenario: Purge uninstall removes reusable auth
- **WHEN** uninstall runs with `--purge-auth`
- **THEN** `ga-kiro-auth` is also removed

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

The dedicated instance is controlled by `GA_MACHINE_NAME` (default `ghost-academy`), `GA_MACHINE_CPUS` (default 4), `GA_MACHINE_MEMORY` (default 8192 MB), and `GA_MACHINE_DISK` (default 60 GB). All five variables SHALL be documented in `docs/configuration.md` and included as commented-out entries in `config/ghostship.conf.example`, with the example's commented value showing how to opt out (`GA_DEDICATED_MACHINE=false`) rather than the (now-default) enabled value. None of the five has a corresponding command-line flag; they are config-file-only, per the `config-file` capability's resolution order (built-in default → config file → flag), with no ambient-environment-variable fallback.

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

#### Scenario: Uninstall on macOS with dedicated machine
- **WHEN** `uninstall.sh` runs, `GA_DEDICATED_MACHINE` is not `false`, and OS is macOS
- **THEN** Ghost Academy containers and volumes are removed from the dedicated machine, and the machine is stopped and removed — unless `--keep-machine` is passed

#### Scenario: Uninstall on Linux with dedicated instance
- **WHEN** `uninstall.sh` runs, `GA_DEDICATED_MACHINE` is not `false`, and OS is Linux
- **THEN** the systemd socket and service units are disabled and removed, and the dedicated storage root is removed — unless `--keep-machine` is passed

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

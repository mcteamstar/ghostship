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
- **THEN** the transport container listens on `9000` (MCP) and `9001` (files), and `GA_PUBLIC_URL` is set to `http://localhost:9001`

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

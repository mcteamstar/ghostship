# trn-cli Specification

## Purpose

The `ghostship` CLI provides a first-class command-line interface for installing, managing, and wiring up a ghostship transport — replacing manual shell-script invocations and JSON-file editing with discoverable, idempotent, scriptable subcommands.
## Requirements
### Requirement: CLI entry point
The system SHALL provide an executable `ghostship` script at the repository root that dispatches to subcommands. The script SHALL use only Python 3 stdlib (no third-party deps). Running `ghostship --help` or `ghostship` with no arguments SHALL print a usage summary listing all available subcommands.

#### Scenario: No arguments
- **WHEN** `ghostship` is invoked with no arguments
- **THEN** usage help is printed and the process exits 0

#### Scenario: Unknown subcommand
- **WHEN** `ghostship unknown-cmd` is invoked
- **THEN** an error message is printed and the process exits non-zero

#### Scenario: Version
- **WHEN** `ghostship version` is invoked
- **THEN** the version string from the `VERSION` file in the repo root is printed and the process exits 0

### Requirement: Transport lifecycle subcommands
The system SHALL provide subcommands that delegate to the shell scripts under `scripts/`. Each subcommand SHALL forward unrecognised flags to the underlying script unchanged. `ghostship install --client-only [flags]` SHALL forward all flags including `--client-only`, `--url`, and `--api-key` to `scripts/install.sh`.

#### Scenario: ghostship install
- **WHEN** `ghostship install [flags]` is invoked
- **THEN** `scripts/install.sh [flags]` runs in the ghostship directory, inheriting stdio, and the exit code is forwarded

#### Scenario: ghostship start
- **WHEN** `ghostship start [flags]` is invoked
- **THEN** `scripts/start.sh [flags]` runs in the ghostship directory and exit code is forwarded

#### Scenario: ghostship stop
- **WHEN** `ghostship stop` is invoked
- **THEN** the `ga-transport` container is stopped; if no container is found, the command exits 0 with a message

#### Scenario: ghostship uninstall
- **WHEN** `ghostship uninstall [flags]` is invoked
- **THEN** `scripts/uninstall.sh [flags]` runs and exit code is forwarded

#### Scenario: ghostship upgrade
- **WHEN** `ghostship upgrade [flags]` is invoked
- **THEN** `scripts/install.sh [flags]` runs (which unconditionally rebuilds images and recreates the transport container) and exit code is forwarded

#### Scenario: ghostship install --client-only forwarded
- **WHEN** `ghostship install --client-only --url https://remote.example.com/mcp --api-key secret` is invoked
- **THEN** `scripts/install.sh --client-only --url https://remote.example.com/mcp --api-key secret` runs and the exit code is forwarded

### Requirement: Transport status
The system SHALL provide `ghostship status` that reports transport health without requiring an MCP connection.

#### Scenario: Transport running
- **WHEN** `ghostship status` is invoked and the `ga-transport` container is running
- **THEN** the output includes `running` status and the port derived from the container's port bindings (via `podman inspect`)

#### Scenario: Transport stopped
- **WHEN** `ghostship status` is invoked and the `ga-transport` container is not running
- **THEN** the output indicates the transport is stopped and exits 0

#### Scenario: Transport not installed
- **WHEN** `ghostship status` is invoked and no `ga-transport` container exists
- **THEN** the output indicates ghostship is not installed and exits 0

### Requirement: Agent wiring via ghostship init
The system SHALL provide `ghostship init` that registers the ghostship MCP server and installs skills into one or more agent clients. The command SHALL be idempotent — safe to run repeatedly.

#### Scenario: Default target (all detected agents)
- **WHEN** `ghostship init` is invoked with no `--agent` flag
- **THEN** the command detects which of kiro-cli and Claude Code are installed on the system and wires each one found

#### Scenario: Targeted agent
- **WHEN** `ghostship init --agent kiro` is invoked
- **THEN** only kiro-cli is wired, regardless of whether Claude Code is present

#### Scenario: Targeted agent claude
- **WHEN** `ghostship init --agent claude` is invoked
- **THEN** only Claude Code is wired, regardless of whether kiro-cli is present

#### Scenario: --agent all
- **WHEN** `ghostship init --agent all` is invoked
- **THEN** both kiro-cli and Claude Code are wired unconditionally (errors for ones not installed are reported per-agent, not fatal)

#### Scenario: Custom URL
- **WHEN** `ghostship init --url http://academy.example.com/mcp` is invoked
- **THEN** the MCP server is registered with that URL instead of `http://localhost:64057/mcp`

#### Scenario: API key provided
- **WHEN** `ghostship init --api-key <key>` is invoked
- **THEN** the MCP server is registered with an `Authorization: Bearer <key>` header in the client config

#### Scenario: MCP server already registered
- **WHEN** `ghostship init` is invoked and a `ghostship` MCP server entry already exists in the client config
- **THEN** the existing entry is updated to match the current URL/key, no duplicate is created, and the command exits 0

#### Scenario: Skill symlinks created
- **WHEN** `ghostship init` successfully wires an agent client
- **THEN** symlinks for `ghostship-command`, `ghostship-admin`, and `ghostship-capability` exist in that client's skills directory pointing into the ghostship repo

#### Scenario: Skill symlinks already present
- **WHEN** `ghostship init` is invoked and skill symlinks already exist
- **THEN** existing symlinks are left in place and no error is raised

#### Scenario: No supported agent found
- **WHEN** `ghostship init` is invoked (no `--agent` flag) and neither kiro-cli nor Claude Code is detected
- **THEN** a clear message is printed and the command exits 0 (not an error)

### Requirement: Auth subcommand group

The system SHALL provide a `ghostship auth` subcommand group that exposes device auth operations directly from the CLI. Running `ghostship auth` with no sub-subcommand SHALL print usage help for the group and exit 0.

Both `auth login` and `auth logout` SHALL accept:
- `--url <transport-url>` — override the transport base URL (default: `GHOSTSHIP_URL` env var, then `http://localhost:64057`)
- `--api-key <key>` — Bearer token for transports that require auth

#### Scenario: ghostship auth — no sub-subcommand
- **WHEN** `ghostship auth` is invoked with no sub-subcommand
- **THEN** usage help for the `auth` group is printed and the process exits 0

#### Scenario: ghostship auth login — success
- **WHEN** `ghostship auth login` is invoked and the transport returns a device code response
- **THEN** the activation URL and user code are printed clearly, the CLI polls until auth completes, and "Authenticated successfully." is printed before exit 0

#### Scenario: ghostship auth login — already authenticated
- **WHEN** `ghostship auth login` is invoked and the transport reports auth is already present
- **THEN** a message such as "Already authenticated." is printed and the process exits 0

#### Scenario: ghostship auth login — timeout
- **WHEN** `ghostship auth login` is invoked but the user does not complete the flow within the polling window (default ~5 min)
- **THEN** a timeout message is printed that includes the activation URL again, and the process exits non-zero

#### Scenario: ghostship auth login — transport unreachable
- **WHEN** `ghostship auth login` is invoked and the transport URL is not reachable
- **THEN** a clear error message is printed (including the URL tried) and the process exits non-zero

#### Scenario: ghostship auth logout — success
- **WHEN** `ghostship auth logout` is invoked
- **THEN** `POST /logout` is called, "Logged out." is printed, and the process exits 0

#### Scenario: ghostship auth logout — transport unreachable
- **WHEN** `ghostship auth logout` is invoked and the transport URL is not reachable
- **THEN** a clear error message is printed and the process exits non-zero

#### Scenario: ghostship auth login — custom URL
- **WHEN** `ghostship auth login --url https://remote.example.com` is invoked
- **THEN** the auth flow targets that URL instead of the default

#### Scenario: ghostship auth login — GHOSTSHIP_URL env var
- **WHEN** `GHOSTSHIP_URL=http://my-host:64057` is set and `ghostship auth login` is invoked without `--url`
- **THEN** the auth flow targets `http://my-host:64057`

### Requirement: PATH availability after install
The system SHALL ensure the `ghostship` command is accessible on `PATH` after a successful install run.

#### Scenario: install.sh symlinks ghostship
- **WHEN** `scripts/install.sh` completes successfully and `~/.local/bin` is on `PATH`
- **THEN** a symlink at `~/.local/bin/ghostship` points to the `ghostship` script in the repo

#### Scenario: ~/.local/bin not on PATH
- **WHEN** `scripts/install.sh` completes and `~/.local/bin` is not on `PATH`
- **THEN** a one-line message is printed explaining how to add it to `PATH`


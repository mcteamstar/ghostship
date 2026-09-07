## Purpose

Provides a lightweight `--client-only` install mode for `scripts/install.sh` that wires the ghostship CLI and agent harnesses onto a machine that connects to a remote transport, without running any container-infrastructure steps.

## ADDED Requirements

### Requirement: --client-only flag accepted by scripts/install.sh
`scripts/install.sh` SHALL accept a `--client-only` flag. When that flag is present the script SHALL skip: the Podman prerequisites check, dedicated machine or network setup, image builds, and `compose up`. No infra steps SHALL execute in client-only mode.

#### Scenario: --client-only skips Podman check
- **WHEN** `scripts/install.sh --client-only` is invoked on a machine where `podman` is not installed
- **THEN** the script does not print a Podman prerequisite error and proceeds without error

#### Scenario: --client-only skips image build
- **WHEN** `scripts/install.sh --client-only` is invoked
- **THEN** no `podman build` or `podman compose` command is executed

#### Scenario: --client-only with unrecognised flags fails early
- **WHEN** `scripts/install.sh --client-only --unknown-flag` is invoked
- **THEN** the script exits with a non-zero status and prints a usage error

### Requirement: ghostship CLI installed in --client-only mode
In `--client-only` mode `scripts/install.sh` SHALL install the `ghostship` CLI to `~/.local/bin/ghostship` using the same symlink logic used by the full install path.

#### Scenario: Symlink created on fresh client-only install
- **WHEN** `scripts/install.sh --client-only` runs and `~/.local/bin/ghostship` does not exist
- **THEN** `~/.local/bin/ghostship` is created as a symlink pointing to the `ghostship` script in the repo and the script exits 0

#### Scenario: Symlink updated on repeated client-only install
- **WHEN** `scripts/install.sh --client-only` runs and a previous `~/.local/bin/ghostship` symlink already exists
- **THEN** the symlink is replaced (or left as-is if already correct) and no error is raised

#### Scenario: ~/.local/bin not on PATH warning
- **WHEN** `scripts/install.sh --client-only` completes and `~/.local/bin` is not on `PATH`
- **THEN** the script prints a one-line message instructing the user to add `~/.local/bin` to `PATH`

### Requirement: ghostship setup invoked in --client-only mode
After installing the CLI symlink, `scripts/install.sh --client-only` SHALL invoke `ghostship setup` with the resolved `--url` and (if provided) `--api-key` values so that all detected agent harnesses (kiro-cli, Claude Code, opencode) are wired.

#### Scenario: Agent wiring with default URL
- **WHEN** `scripts/install.sh --client-only` is invoked without `--url`
- **THEN** `ghostship setup` is called with `--url http://localhost:64057/mcp` and wires any detected agent clients

#### Scenario: Agent wiring with custom URL
- **WHEN** `scripts/install.sh --client-only --url https://academy.example.ts.net/mcp` is invoked
- **THEN** `ghostship setup` is called with `--url https://academy.example.ts.net/mcp`

#### Scenario: Agent wiring with API key
- **WHEN** `scripts/install.sh --client-only --api-key <key>` is invoked
- **THEN** `ghostship setup` is called with `--api-key <key>` and registers the MCP entry with a bearer-token header

#### Scenario: No supported agent found
- **WHEN** `scripts/install.sh --client-only` is invoked and neither kiro-cli nor Claude Code nor opencode is detected
- **THEN** `ghostship setup` reports no agents wired and `scripts/install.sh` exits 0

### Requirement: --client-only is idempotent
Running `scripts/install.sh --client-only` multiple times on the same machine SHALL produce the same end state as running it once. Repeated runs SHALL NOT accumulate duplicate MCP entries or duplicate symlinks.

#### Scenario: Repeated client-only run is a no-op
- **WHEN** `scripts/install.sh --client-only` is run a second time with the same arguments on a machine already wired by a prior run
- **THEN** the script exits 0 and produces no errors; agent configs contain exactly one ghostship MCP entry

### Requirement: --url and --api-key accepted in --client-only mode
`scripts/install.sh` SHALL accept `--url <transport-url>` and `--api-key <key>` flags when `--client-only` is set. These flags SHALL be forwarded to `ghostship setup`.

#### Scenario: --url flag accepted
- **WHEN** `scripts/install.sh --client-only --url https://remote.example.com/mcp` is invoked
- **THEN** the script accepts the flag without error and passes the URL to `ghostship setup`

#### Scenario: --api-key flag accepted
- **WHEN** `scripts/install.sh --client-only --api-key secrettoken` is invoked
- **THEN** the script accepts the flag without error and passes the key to `ghostship setup`

### Requirement: Documentation covers client-only install
`README.md` and `docs/configuration.md` SHALL each include a "Client-only install" section describing the `--client-only` flag, the `--url` and `--api-key` options, and a one-liner example invocation.

#### Scenario: Developer consults README for client-only install steps
- **WHEN** a developer reads `README.md`
- **THEN** they find a concise section that explains `--client-only` mode and shows an example command

#### Scenario: Operator consults configuration docs for client-only flags
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they find `--url` and `--api-key` documented under a "Client-only install" heading with their defaults and purpose

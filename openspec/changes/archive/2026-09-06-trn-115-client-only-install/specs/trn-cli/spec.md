## MODIFIED Requirements

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

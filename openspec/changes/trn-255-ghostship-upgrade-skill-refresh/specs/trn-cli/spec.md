# Spec Delta

## MODIFIED Requirements

### Requirement: Transport lifecycle subcommands
The system SHALL provide subcommands that delegate to the shell scripts under `scripts/`. Each subcommand SHALL forward unrecognised flags to the underlying script unchanged. `ghostship install --client-only [flags]` SHALL forward all flags including `--client-only`, `--url`, and `--api-key` to `scripts/install.sh`.

`ghostship stop` SHALL stop the `ga-transport` container, the `ga-portal` container, and the underlying Podman machine or dedicated service, in that order. On macOS with a dedicated machine (`GA_DEDICATED_MACHINE` not `false`), stopping the machine is `podman machine stop <GA_MACHINE_NAME>`. On Linux with a dedicated service, stopping is `systemctl --user stop podman-<GA_MACHINE_NAME>.service` (or the equivalent socket unit). On Linux without a dedicated service, the default Podman socket service is stopped. All crew containers and volumes are preserved across the stop; `ghostship start` restores the machine and transport, and crews restart transparently on next use via `_ensure_crew_running`. If the machine is already stopped or not found, `ghostship stop` SHALL exit 0 with a diagnostic message rather than failing.

`ghostship upgrade` SHALL accept a `--skills` flag. When `--skills` is given, after the transport rebuild completes successfully, `ghostship upgrade` SHALL invoke `ghostship setup` to refresh skill symlinks and re-register the MCP server for all detected agent clients. When `--skills` is omitted, behaviour is unchanged.

#### Scenario: ghostship install
- **WHEN** `ghostship install [flags]` is invoked
- **THEN** `scripts/install.sh [flags]` runs in the ghostship directory, inheriting stdio, and the exit code is forwarded

#### Scenario: ghostship start
- **WHEN** `ghostship start [flags]` is invoked
- **THEN** `scripts/start.sh [flags]` runs in the ghostship directory and exit code is forwarded

#### Scenario: ghostship stop
- **WHEN** `ghostship stop` is invoked on macOS with a dedicated machine
- **THEN** `ga-transport` is stopped, `ga-portal` is stopped, and `podman machine stop <GA_MACHINE_NAME>` is called; the command exits 0

#### Scenario: ghostship stop on Linux with dedicated service
- **WHEN** `ghostship stop` is invoked on Linux with `GA_DEDICATED_MACHINE` not `false`
- **THEN** `ga-transport` is stopped, `ga-portal` is stopped, and `systemctl --user stop podman-<GA_MACHINE_NAME>.service` (or equivalent) is called; the command exits 0

#### Scenario: ghostship stop — machine already stopped
- **WHEN** `ghostship stop` is invoked and the Podman machine is already stopped
- **THEN** the command exits 0 with a message; it does not fail

#### Scenario: ghostship stop — no container found
- **WHEN** `ghostship stop` is invoked and neither `ga-transport` nor the Podman machine exists
- **THEN** the command exits 0 with a message

#### Scenario: ghostship start after stop restores crews
- **WHEN** `ghostship stop` is followed by `ghostship start`
- **THEN** the Podman machine or service restarts, the transport container restarts, and existing crew containers that were running before the stop are accessible again via `_ensure_crew_running` on next use

#### Scenario: ghostship uninstall
- **WHEN** `ghostship uninstall [flags]` is invoked
- **THEN** `scripts/uninstall.sh [flags]` runs and exit code is forwarded

#### Scenario: ghostship upgrade without --skills
- **WHEN** `ghostship upgrade [flags]` is invoked without `--skills`
- **THEN** `scripts/install.sh [flags]` runs (which unconditionally rebuilds images and recreates the transport container) and exit code is forwarded; no skill refresh is performed

#### Scenario: ghostship upgrade with --skills
- **WHEN** `ghostship upgrade --skills` is invoked and the transport rebuild succeeds
- **THEN** `scripts/install.sh` runs, then `ghostship setup` runs for all detected agent clients, and the combined exit code is forwarded

#### Scenario: ghostship upgrade --skills — install fails
- **WHEN** `ghostship upgrade --skills` is invoked and `scripts/install.sh` exits non-zero
- **THEN** `ghostship setup` is NOT run and the non-zero exit code is forwarded

#### Scenario: ghostship install --client-only forwarded
- **WHEN** `ghostship install --client-only --url https://remote.example.com/mcp --api-key secret` is invoked
- **THEN** `scripts/install.sh --client-only --url https://remote.example.com/mcp --api-key secret` runs and the exit code is forwarded

## ADDED Requirements

### Requirement: Skills subcommand
The system SHALL provide a `ghostship skills` subcommand that is a direct alias for `ghostship setup`. It SHALL accept the same flags (`--agent`, `--url`, `--api-key`) and behave identically. It exists to give a discoverable, intent-clear entry point for "refresh my skills" without implying a full reinstall.

#### Scenario: ghostship skills — no flags
- **WHEN** `ghostship skills` is invoked with no flags
- **THEN** it behaves identically to `ghostship setup` with no flags: auto-detects installed agent clients and refreshes skill symlinks and MCP registration for each

#### Scenario: ghostship skills --agent kiro
- **WHEN** `ghostship skills --agent kiro` is invoked
- **THEN** it behaves identically to `ghostship setup --agent kiro`

#### Scenario: ghostship skills --help
- **WHEN** `ghostship skills --help` is invoked
- **THEN** usage text is printed explaining it refreshes skill symlinks and is equivalent to `ghostship setup`

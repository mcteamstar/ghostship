## Why

`install.sh` today always runs the full stack — Podman prerequisites, machine/network setup, image builds, and the transport container. There is no supported path for a developer whose machine connects to a shared remote academy to get just the CLI, skills, and MCP entry wired up in seconds without touching infra.

## What Changes

- Add `--client-only` flag to `scripts/install.sh` that skips: Podman prerequisites check, dedicated machine/network setup, image builds, and `compose up`.
- In `--client-only` mode, `scripts/install.sh` SHALL: install `~/.local/bin/ghostship` (symlink to the repo `ghostship` script), then call `ghostship setup` to wire skills and register the MCP entry for all detected agent clients (kiro-cli, Claude Code, opencode).
- `--client-only` accepts `--url <transport-url>` (default `http://localhost:64057/mcp`) and `--api-key <key>` to configure which transport the client connects to.
- `ghostship install --client-only` delegates to `scripts/install.sh --client-only` via the existing CLI dispatch, forwarding all flags.
- The root `install.sh` shim forwards `--client-only` unchanged to `scripts/install.sh`.
- `opencode` is already handled by `scripts/setup.py`; `--client-only` mode calls `ghostship setup` with no `--agent` restriction so all three are wired.

## Capabilities

### New Capabilities

- `installation/client-only`: Lightweight `--client-only` mode for `scripts/install.sh` that installs the ghostship CLI and wires agent harnesses without any infra setup.

### Modified Capabilities

- `installation`: Existing install spec gains the `--client-only` flag behaviour, the resolution of `--url`/`--api-key` in that mode, and the idempotency contract for repeated client-only runs.
- `trn-cli`: `ghostship install --client-only` must forward the flag through to `scripts/install.sh`; the `ghostship setup` subcommand is already specified but the delegation from `--client-only` install mode is a new scenario.

## Impact

- `scripts/install.sh`: new flag branch; existing full-install path is unchanged.
- `ghostship` CLI entry point: no new subcommand; existing `install` and `setup` dispatch already covers the surface.
- `scripts/setup.py`: no changes required; it already handles kiro, claude, and opencode.
- Docs: `README.md` and `docs/configuration.md` need a short "Client-only install" section.
- No transport-side changes; no Containerfile changes; no compose changes.

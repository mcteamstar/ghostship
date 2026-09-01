## Why

Setting up ghostship requires running shell scripts, manually editing JSON config files for each agent client, and symlinking skill directories — none of it is discoverable or scriptable. A `ghostship` CLI makes installation, lifecycle management, and agent wiring first-class, composable, and idempotent.

## What Changes

- New `ghostship` Python script at the repo root (stdlib-only, no new deps)
- **BREAKING**: `start.sh` and `uninstall.sh` moved to `scripts/` — direct invocations must be updated
- `install.sh` remains at the repo root as a shim that calls `scripts/install.sh "$@"` — existing workflows and docs continue to work
- `ghostship install` — wraps `scripts/install.sh` with forwarded flags
- `ghostship start` — wraps `scripts/start.sh`
- `ghostship stop` — stops the `ga-transport` container
- `ghostship status` — shows transport health and active crew count without needing the MCP server
- `ghostship upgrade` — rebuilds images and restarts the transport (equivalent to a fresh `scripts/install.sh` run)
- `ghostship uninstall` — wraps `scripts/uninstall.sh`
- `ghostship init` — detects installed agent clients (kiro-cli, Claude Code), registers the `ghostship` MCP server in each, and symlinks the three skills (`ghostship-command`, `ghostship-admin`, `ghostship-capability`); idempotent and supports `--agent kiro|claude|all`, `--url`, `--api-key` flags
- `ohnomer/servers` deploy updated to call `./ghostship install` instead of `bash "$GHOSTSHIP_DIR/install.sh"`

## Capabilities

### New Capabilities

- `trn-cli`: The `ghostship` CLI — subcommands, flag handling, agent wiring, and output contract

### Modified Capabilities

- `installation`: `install.sh` gains a post-install step that makes `ghostship` executable on `PATH` (symlink into `~/.local/bin` or print a `PATH` hint)

## Impact

- New file: `ghostship` (Python script, repo root)
- New directory: `scripts/` containing `install.sh` (real implementation), `start.sh`, `uninstall.sh`
- `install.sh` at repo root becomes a one-line shim: `exec "$(dirname "$0")/scripts/install.sh" "$@"`
- `start.sh` and `uninstall.sh` removed from repo root (**BREAKING** for direct callers)
- Modified file: `ohnomer/servers` — `hyperv/academy/install.sh` updated to call `./ghostship install`
- No transport code changes; no new Python dependencies (stdlib only)
- kiro-cli MCP config: invokes `kiro-cli mcp add`
- Claude Code MCP config: reads/writes `~/.claude.json` (or `~/.config/claude/claude.json`)
- Skill wiring: creates symlinks under `~/.kiro/skills/` and `~/.claude/skills/`

## Context

`scripts/install.sh` is a single bash script (~600 lines) that handles the full install flow: argument parsing, Podman prerequisites, machine/network setup, image builds, secret/key management, compose file generation, and transport startup. The argument parser is a hand-rolled `while [[ $# -gt 0 ]]` loop. The CLI entry point (`ghostship`) already dispatches `install` to `scripts/install.sh` via `_exec_script`, forwarding all extra args. `ghostship setup` (via `scripts/setup.py`) already handles kiro-cli, Claude Code, and opencode, including auto-detection when `--agent` is omitted.

See `proposal.md — Why` for motivation.

## Goals / Non-Goals

**Goals:**
- Add `--client-only` branch to `scripts/install.sh` that exits the infra path early after installing the CLI symlink and calling `ghostship setup`.
- Accept `--url` and `--api-key` in `--client-only` mode and forward them to `ghostship setup`.
- Keep the full install path entirely unchanged.
- Keep the `ghostship install` CLI dispatch unchanged (flags flow through already).

**Non-Goals:**
- No new `ghostship` subcommand.
- No changes to `scripts/setup.py`.
- No transport-side, Containerfile, or compose changes.
- No new config-file variables.

## Decisions

### Decision 1: --client-only as a flag in scripts/install.sh rather than a separate script

**Choice**: Add a `CLIENT_ONLY=false` default at the top of `scripts/install.sh` and a `--client-only` case in the argument parser. After parsing, gate the entire infra block behind `if ! $CLIENT_ONLY; then ... fi`. The client-only path runs only the CLI symlink step and a `ghostship setup` invocation.

**Alternatives considered**:
- A separate `scripts/install-client.sh`: would duplicate the argument parser and symlink logic; adds a second entry point to maintain.
- A new `ghostship` subcommand (e.g. `ghostship client-install`): the ticket asks for `--client-only` on `install.sh`; a separate subcommand diverges from that without benefit.

**Rationale**: Minimal diff to the existing script. One flag, one conditional block. The full install path is structurally unaffected.

### Decision 2: --url defaults to http://localhost:64057/mcp

**Choice**: Default `CLIENT_ONLY_URL="http://localhost:64057/mcp"`. Overridden by `--url`.

**Rationale**: Matches the existing default port in the full install path. A developer who forgets `--url` on a machine with a local transport will still wire correctly. If no local transport is running, `ghostship setup` records the URL in the agent config and the transport can be pointed at later.

### Decision 3: Invoke ghostship setup via the symlink, not by calling scripts/setup.py directly

**Choice**: After the symlink is created, call `"$HOME/.local/bin/ghostship" setup --url "$CLIENT_ONLY_URL" ${CLIENT_ONLY_API_KEY:+--api-key "$CLIENT_ONLY_API_KEY"}`.

**Alternatives considered**:
- Call `python3 "$GHOSTSHIP_DIR/scripts/setup.py"` directly: works but bypasses the CLI entry point and could break if the dispatch logic changes.
- Call `"$GHOSTSHIP_DIR/ghostship" setup ...`: correct, but if `~/.local/bin` is not yet on `PATH` the user would still get a working install. Using the repo-local ghostship directly is cleaner and avoids the PATH-not-updated window.

**Rationale**: Calling the repo-local `ghostship` binary directly (not through `PATH`) is the most reliable — it works before `~/.local/bin` is on `PATH` and picks up the correct repo path regardless of environment.

### Decision 4: No new config-file variables for --client-only

**Choice**: `--client-only`, `--url`, and `--api-key` are flag-only in client-only mode; they are not added to `config/ghostship.conf.example` or `docs/configuration.md`'s variable table.

**Rationale**: Client-only installs are one-shot wiring operations. Persisting them in a config file adds complexity for a use-case where re-running the command is trivially cheap. The `--api-key` and `--url` values are persisted in the agent config files by `ghostship setup` itself.

## Risks / Trade-offs

- **ghostship not yet on PATH when setup is called** → Mitigation: call `"$GHOSTSHIP_DIR/ghostship"` (the repo-local binary) directly rather than relying on `PATH`.
- **scripts/setup.py fails if no agent is found** → Already handled: `ghostship setup` exits 0 with a message when no agents are detected. No extra handling needed.
- **--url typo points client at wrong transport** → Not mitigated at install time; the URL is validated lazily when the agent client first makes an MCP call. Acceptable: same behavior as `ghostship setup --url`.
- **Full install accidentally picks up --client-only in env** → Not possible: `CLIENT_ONLY` is a local variable set to `false` as a built-in default at the top of the script; there is no ambient environment variable fallback.

## Migration Plan

No migration needed. The change is additive — `--client-only` is a new opt-in flag; no existing invocation is affected.

## Open Questions

None. The flag interface, delegation path, and scope are fully specified.

## Context

See proposal.md — Why. Current state: three shell scripts (`install.sh`, `start.sh`, `uninstall.sh`) plus manual JSON editing for MCP registration. No single entry point, no agent-wiring automation.

Key constraints:
- Must work on macOS and Linux with no additional dependencies beyond Python 3 (already required by the transport venv)
- `ghostship init` touches kiro-cli config (`~/.kiro/settings.json`) and Claude Code config (`~/.claude.json`) — both are JSON files the user may have customised; edits must be surgical and idempotent
- Skill symlinking must not break if the repo is moved later (symlinks are relative to the repo path at init time — document this)

## Goals / Non-Goals

**Goals:**
- Single `ghostship` dispatcher script with lifecycle and wiring subcommands
- Idempotent `ghostship init` that wires MCP + skills for kiro-cli and/or Claude Code
- `scripts/install.sh` symlinks `ghostship` into `~/.local/bin` after success
- No new runtime dependencies

**Non-Goals:**
- `ghostship init` does not handle the `/login` kiro-cli auth flow (that's a separate interactive step already documented in `ghostship-admin`)
- No Windows support (Podman on Windows is unsupported)
- No remote-transport init (init always registers against a URL, defaulting to localhost; remote configuration is the operator's responsibility)
- The CLI does not replace `install.sh`/`start.sh`/`uninstall.sh` — it wraps them

## Decisions

### D1: Python, not bash
**Decision:** `ghostship` is a Python 3 script (no shebang venv; uses `#!/usr/bin/env python3`).

**Rationale:** `ghostship init` needs to read/write JSON config files for kiro-cli and Claude Code. Bash JSON manipulation (via `jq` or `sed`) is fragile; Python stdlib `json` + `pathlib` handles it cleanly. Python 3 is already on any machine that can run the transport (required by the venv).

**Alternative considered:** Pure bash with `jq`. Rejected: `jq` is not universally installed and bash + JSON is error-prone for nested edits.

### D2: Lifecycle subcommands delegate to shell scripts, not re-implement them
**Decision:** `ghostship install/start/upgrade/uninstall` use `subprocess.execvp` to hand off to the scripts under `scripts/` with all flags forwarded.

**Rationale:** The shell scripts handle all platform-specific Podman logic (macOS machine vs Linux socket, config discovery, etc.). Duplicating that in Python would be a maintenance burden. The CLI is a thin dispatch layer.

**Alternative considered:** Rewrite lifecycle in Python. Rejected: the shell scripts are well-tested and the platform logic is non-trivial.

### D2a: install.sh shim at root; start.sh and uninstall.sh move
**Decision:** `start.sh` and `uninstall.sh` move to `scripts/` with no root presence. `install.sh` stays at the root as a one-line shim (`exec "$(dirname "$0")/scripts/install.sh" "$@"`) — the real implementation moves to `scripts/install.sh`.

**Rationale:** `install.sh` at the root has deep reach — external docs, README, tutorials, the ghostship-admin skill, operator muscle memory. Breaking that unnecessarily creates friction for no benefit. `start.sh` and `uninstall.sh` are lower-traffic and less externally referenced. The deploy path in `ohnomer/servers` already calls `bash "$GHOSTSHIP_DIR/install.sh"` — updating it to `"$GHOSTSHIP_DIR/ghostship" install` is the right migration, and the shim means it continues to work even if that change lags.

### D3: ghostship stop uses podman directly
**Decision:** `ghostship stop` invokes `podman stop ga-transport` (using the same Podman command resolution logic as `start.sh` — honouring `GA_MACHINE_NAME` / podman-machine on macOS).

**Rationale:** No `stop.sh` exists; the stop operation is simple enough to implement directly without a new shell script.

### D4: ghostship init writes MCP config surgically
**Decision:** For kiro-cli, `ghostship init` invokes `kiro-cli mcp add --name ghostship --url <url> --scope global` (idempotent add) rather than editing `~/.kiro/settings.json` directly. For Claude Code, it reads/writes `~/.claude.json` using Python `json`, merging only the `mcpServers.ghostship` key.

**Rationale:** Using the kiro-cli CLI for kiro avoids depending on kiro's internal config schema. Claude Code has no equivalent CLI for MCP registration, so direct JSON editing is required. Surgical merge (not full replacement) protects user customisations in `~/.claude.json`.

**kiro-cli update behaviour:** `kiro-cli mcp add` on an already-registered name updates the entry in recent versions; if that fails, the script falls back to removing and re-adding.

### D5: Skill wiring via symlinks, not copies
**Decision:** `ghostship init` creates symlinks in `~/.kiro/skills/` and `~/.claude/skills/` pointing to the skills under `.claude-plugin/skills/` in the repo.

**Rationale:** Symlinks mean the skills stay current when the repo is updated. Copies would go stale. This matches the manual instructions already in `ghostship-admin`.

**Caveat:** If the repo is moved after init, the symlinks break. Document this; the fix is `ghostship init` again from the new location.

### D6: install.sh PATH wiring
**Decision:** At the end of a successful `install.sh` run, create `~/.local/bin/ghostship` as a symlink to `<ghostship-dir>/ghostship`. Print a PATH hint if `~/.local/bin` is not in `$PATH`.

**Rationale:** `~/.local/bin` is the standard user-local binary directory on Linux and macOS (XDG spec; Homebrew adds it on macOS). Creating it and linking there avoids requiring `sudo` or modifying system paths.

## Risks / Trade-offs

- **kiro-cli schema change** → `kiro-cli mcp add` API could change. Mitigation: use the CLI command, not direct file editing, so the risk is bounded to CLI compatibility.
- **Claude Code config location** → Claude Code may use `~/.config/claude/claude.json` on some platforms. Mitigation: check both paths; use whichever exists; create `~/.claude.json` if neither exists.
- **Symlinks break on repo move** → Documented in `ghostship-admin` skill. The fix is `ghostship init` again. Not auto-healed.
- **install.sh ~1000 lines** → Adding PATH wiring at the end is low-risk (it's additive), but it must not interfere with the existing error-exit paths. Mitigation: add the PATH step inside the `main()` function after the existing success log line.

## Open Questions

- Should `ghostship status` also hit the `/health` endpoint over HTTP to confirm the transport is reachable (not just that the container is running)? Left to implementation — the container-running check covers the common case; HTTP health check is a nice-to-have.
- Should `ghostship init` also optionally run `POST /login` if the transport is detected as unauthenticated? Left to implementation — out of scope for this ticket but a natural follow-on.

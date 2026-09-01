## 1. Move scripts and ghostship scaffold

- [x] 1.1 Create `scripts/` directory; move `start.sh` and `uninstall.sh` into it (preserve execute bit)
- [x] 1.2 Move `install.sh` to `scripts/install.sh`; replace root `install.sh` with a one-line shim: `exec "$(dirname "$0")/scripts/install.sh" "$@"`
- [x] 1.3 Create `ghostship` executable Python script at the repo root with `#!/usr/bin/env python3` shebang and `chmod +x`
- [x] 1.4 Implement top-level argument parsing: dispatch to subcommand handlers, print usage on no args or `--help`, exit non-zero on unknown subcommands
- [x] 1.5 Add `version` subcommand that prints the current `VERSION` file content

## 2. Lifecycle subcommands

- [x] 2.1 Implement `ghostship install [flags]` — exec `scripts/install.sh` from the ghostship directory with all flags forwarded
- [x] 2.2 Implement `ghostship start [flags]` — exec `scripts/start.sh` with all flags forwarded
- [x] 2.3 Implement `ghostship upgrade [flags]` — exec `scripts/install.sh` with all flags forwarded (alias with a clear description)
- [x] 2.4 Implement `ghostship uninstall [flags]` — exec `scripts/uninstall.sh` with all flags forwarded
- [x] 2.5 Implement `ghostship stop` — run `podman stop ga-transport`, exit 0 if the container is not found

## 3. Status subcommand

- [x] 3.1 Implement `ghostship status` — check whether `ga-transport` container exists and is running using `podman ps`/`podman inspect`
- [x] 3.2 When running: print status, port (from `podman inspect ga-transport` port bindings), and uptime
- [x] 3.3 When stopped/missing: print a clear human-readable message; exit 0

## 4. ghostship init — MCP registration

- [x] 4.1 Implement `--agent` flag parsing: `kiro`, `claude`, `all`; default to auto-detect both
- [x] 4.2 Implement `--url` flag (default `http://localhost:64057/mcp`) and `--api-key` flag
- [x] 4.3 Implement kiro-cli detection: check if `kiro-cli` is on `PATH`
- [x] 4.4 Implement kiro-cli MCP registration: invoke `kiro-cli mcp add --name ghostship --url <url> --scope global`; when `--api-key` is set also pass `--headers '{"Authorization": "Bearer <key>"}'`; if the name already exists, remove and re-add (idempotent)
- [x] 4.5 Implement Claude Code detection: check for `~/.claude.json` or `~/.config/claude/claude.json`
- [x] 4.6 Implement Claude Code MCP registration: read the JSON file, merge `mcpServers.ghostship` key (create the file if neither path exists), write back atomically

## 5. ghostship init — skill wiring

- [x] 5.1 Implement skill symlink helper: given a client's skills directory and the repo's `.claude-plugin/skills/` path, create symlinks for `ghostship-command`, `ghostship-admin`, `ghostship-capability`
- [x] 5.2 Wire skill symlinks for kiro-cli into `~/.kiro/skills/`
- [x] 5.3 Wire skill symlinks for Claude Code into `~/.claude/skills/`
- [x] 5.4 Skip existing symlinks without error; print a note if a symlink target has changed (repo was moved)

## 6. scripts/install.sh PATH wiring and deploy update

- [x] 6.1 At the end of `scripts/install.sh`'s success path, create `~/.local/bin/` if it doesn't exist and symlink `ghostship` there
- [x] 6.2 If `~/.local/bin` is not on `$PATH`, print a one-line instruction: `Add ~/.local/bin to your PATH: export PATH="$HOME/.local/bin:$PATH"`
- [ ] 6.3 Update `ohnomer/servers` — `hyperv/academy/install.sh`: replace `bash "$GHOSTSHIP_DIR/install.sh"` with `"$GHOSTSHIP_DIR/ghostship" install` (using the CLI as the entry point)

## 7. Tests and validation

- [x] 7.1 Validate the script runs and prints help: `./ghostship --help`
- [x] 7.2 Validate `ghostship status` works when transport is running and when stopped
- [x] 7.3 Validate `ghostship init` is idempotent: run twice, confirm no duplicates in kiro/Claude configs
- [x] 7.4 Validate `ghostship init --api-key <key>` sets the header correctly in both client configs
- [x] 7.5 Validate `ghostship stop` exits 0 when container is not present
- [x] 7.6 Run `openspec validate trn-88-ghostship-cli --strict`
- [x] 7.7 Update `ghostship-admin` SKILL.md to mention `ghostship init` and `ghostship status` as the CLI entry points for the setup and health-check workflows

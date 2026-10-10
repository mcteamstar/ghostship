## Why

TRN-167 added Claude Code as an ACP backend but requires `GA_CREW_ANTHROPIC_API_KEY` — an Anthropic API key with pay-per-token billing. Users with Claude Pro/Max subscriptions cannot use the Claude backend without also maintaining a separate API-tier account. Adding an OAuth device-code flow (mirroring the existing kiro-cli login path) lets subscription users authenticate once and reuse credentials across all Claude-backend crews, with no API key required.

## What Changes

- **New `POST /login/claude` and `GET /login/claude` endpoints** — a Claude-specific login state machine, parallel to the existing kiro-cli login endpoints. `POST /login/claude` starts a `claude auth login` device-code flow inside an ephemeral container (via PTY, same technique as `_initiate_login`), returns a `login_url` and `code`. `GET /login/claude` polls for completion and writes `ga-claude-auth` when done.
- **New `ga-claude-auth` credential file** — analogous to `ga-kiro-auth`. Written to `DATA_DIR/ga-claude-auth` (mode 0600) on login completion; contains the Claude Code OAuth token/session data that can be injected into crew containers.
- **`GA_CREW_ANTHROPIC_API_KEY` becomes optional** — when `GA_CREW_ACP_BACKEND=claude`, the transport accepts either `GA_CREW_ANTHROPIC_API_KEY` (API key path, as before) or a valid `ga-claude-auth` file (OAuth path). If neither is present, `launch` returns `not_authenticated` with a `login_url`. The startup `ConfigError` for missing API key is relaxed: only fail if neither credential source is available at first `launch`, not at startup.
- **Claude auth injection into crew containers** — at `launch` time, the Claude OAuth credential from `ga-claude-auth` is copied into the crew container's `~/.claude/` directory (the path Claude Code reads for its session), replacing the env-var injection for the OAuth path.
- **PTY interaction for `claude auth login`** — `claude auth login --device` (or equivalent headless flag) produces interactive prompts. The PTY approach from `_initiate_login` is reused: exec with `container_exec_pty_stdin`, read output, answer any prompts, extract the device URL.
- **`POST /logout/claude`** — clears `ga-claude-auth` and wipes the Claude credential from all running Claude-backend crews, parallel to `POST /logout`.

## Capabilities

### New Capabilities

- `claude-auth`: Claude Code OAuth device-code login flow, credential storage (`ga-claude-auth`), injection into crew containers, and logout — parallel to the existing kiro auth state machine.

### Modified Capabilities

- `crew-auth`: The auth injection requirement for the Claude backend changes: `GA_CREW_ANTHROPIC_API_KEY` is no longer required when `ga-claude-auth` is present. The Claude backend auth path now has two sub-paths: API key (env var) or OAuth (credential file injection).
- `crew-acp-backend`: The validation requirement changes: `GA_CREW_ANTHROPIC_API_KEY` is no longer mandatory at startup for the Claude backend; the transport also accepts a valid `ga-claude-auth` credential file. `launch` is the enforcement point, not startup.

## Impact

- `transport/server.py` — two new route pairs: `POST/GET /login/claude`, `POST /logout/claude`; relaxed startup config validation
- `transport/lifecycle.py` — new `_initiate_claude_login`, `_inject_claude_auth`, `_nuke_claude_login_container` functions; `_finish_crew_setup` Claude branch extended to handle OAuth credential injection
- `transport/config.py` — `GA_CREW_ANTHROPIC_API_KEY` validation moved from startup to launch-time; new `ga_claude_auth_path` helper
- `scripts/install.sh` — no image changes needed (claude CLI already in the Claude-enabled image)
- `docs/auth.md` — document the Claude OAuth flow
- `docs/configuration.md` — update `GA_CREW_ANTHROPIC_API_KEY` to note it is optional when OAuth credentials exist

## Context

TRN-167 added Claude Code as an ACP backend but requires `GA_CREW_ANTHROPIC_API_KEY` — a pay-per-token API key. The kiro-cli auth path uses a PTY-based device-code flow (`_initiate_login`, `container_exec_pty_stdin`) that runs `kiro-cli login --use-device-flow` inside an ephemeral `ga-login-*` container, reads the output stream for a verification URL, and stores credentials in `ga-kiro-auth`. This change adds an equivalent flow for Claude Code using the same PTY infrastructure.

The Claude Code CLI (`claude`) supports `claude auth login` for OAuth device-code authentication. It writes credentials to `~/.claude/` (a JSON file). The `claude-agent-acp` ACP server reads from that same directory when authenticating against `api.anthropic.com`. This means injecting `~/.claude/` contents into a crew container is sufficient for OAuth-authenticated Claude sessions — no env var needed.

`GA_CREW_ANTHROPIC_API_KEY` validation is currently a hard `ConfigError` at startup (`Config.validate()`). This must be relaxed to a lazy check at `launch` time so operators can start the transport before authenticating.

## Goals / Non-Goals

**Goals:**
- Claude OAuth device-code flow via `POST /login/claude` + `GET /login/claude`, parallel to kiro
- `ga-claude-auth` credential file for cross-crew reuse, parallel to `ga-kiro-auth`
- Credential injection into crew containers via `~/.claude/` copy at setup time
- `POST /logout/claude` to clear credentials and wipe running crews
- Relax `GA_CREW_ANTHROPIC_API_KEY` startup validation to launch-time
- API key path continues to work unchanged (precedence over OAuth)

**Non-Goals:**
- Per-crew auth (transport-wide credential, same as kiro)
- Credential rotation in running crews without restart
- Supporting Claude OAuth alongside a non-claude ACP backend

## Decisions

### D1: Reuse PTY infrastructure verbatim

`_initiate_claude_login` mirrors `_initiate_login` exactly: spawn `ga-claude-login-<token>` container from the Claude-enabled spec-ops image (which has `claude` CLI installed), exec `claude auth login` via `container_exec_pty_stdin`, read the PTY output stream with `select()`, extract the verification URL, drain in background. The 45-second deadline applies.

**Why:** The PTY approach already handles the interactive-terminal requirement. `claude auth login` behaves similarly to `kiro-cli login` — it prints a URL and waits for browser approval. No need for a different mechanism.

**Container image:** The `ga-claude-login-*` container uses the spec-ops image (which has `claude` installed when built with `GA_INCLUDE_CLAUDE_AGENT=true`), not the upstream kiro image used for `ga-login-*`. This is a pre-condition: Claude OAuth login requires a Claude-enabled image.

### D2: ga-claude-auth stores ~/.claude/ as a tar archive

`kiro-cli` auth state is a flat SQLite row that `inject_auth.py` writes row-by-row. Claude Code's auth state is a directory (`~/.claude/`) containing JSON files. Rather than parse or understand the internals, store the entire `~/.claude/` directory as a tar archive in `ga-claude-auth`. Injection: `podman cp` or `container_exec` to untar into the crew container's `~/.claude/`.

**Alternative considered:** Store only the specific credential JSON file. Rejected: the exact filename and format are internal to the `claude` CLI and may change. Storing the full directory is forward-compatible.

### D3: API key takes precedence over OAuth credential

When both `GA_CREW_ANTHROPIC_API_KEY` and `ga-claude-auth` are present, the API key wins. This is consistent with how `KIRO_API_KEY` takes precedence over `ga-kiro-auth` in the kiro path.

### D4: Startup ConfigError for missing API key is removed; launch enforces lazily

`Config.validate()` currently raises `ConfigError` if `GA_CREW_ACP_BACKEND=claude` and `GA_CREW_ANTHROPIC_API_KEY` is unset. This check is removed. Instead, `launch()` checks: if `GA_CREW_ACP_BACKEND=claude` and neither `GA_CREW_ANTHROPIC_API_KEY` nor a valid `ga-claude-auth` is present, it automatically calls `_initiate_claude_login` and returns `not_authenticated` with the login URL — identical behaviour to the kiro path when unauthenticated.

### D5: Claude login container uses spec-ops image, not upstream kiro image

The ephemeral login container for kiro uses the upstream `ghcr.io/kirodotdev/kirocrew` image because only `kiro-cli` is needed. For Claude, the `claude` CLI is only present in the spec-ops image when built with `GA_INCLUDE_CLAUDE_AGENT=true`. The Claude login container therefore uses `localhost/spec-ops:latest`. This means `POST /login/claude` will fail with a clear error if the operator has not built a Claude-enabled image.

### D6: Logout wipes ~/.claude/ from running Claude-backend crews

`POST /logout/claude` deletes `ga-claude-auth` and, for each running crew with `acp_backend=claude`, executes `rm -rf ~/.claude/` inside the container. This mirrors how `POST /logout` runs `DELETE FROM auth_kv` in kiro crews.

## Risks / Trade-offs

- **Pre-condition: Claude-enabled image required** — `POST /login/claude` fails if the spec-ops image was not built with `GA_INCLUDE_CLAUDE_AGENT=true`. Mitigation: return a clear error message naming the missing build flag.
- **~/.claude/ format opacity** — storing the directory as a tar means a `claude` CLI upgrade that changes its credential format may produce incompatible archives. Mitigation: `ga-claude-auth` is easily re-generated by re-logging in; it is not a long-lived secret.
- **PTY URL extraction brittleness** — `claude auth login` output format may differ from `kiro-cli login`. The URL regex pattern must be confirmed against the actual `claude` CLI output during implementation (task 1.2).

## Migration Plan

1. Operators already using `GA_CREW_ANTHROPIC_API_KEY`: no change required. The API key path continues to work exactly as before.
2. Operators wanting subscription OAuth: build a Claude-enabled image (`GA_INCLUDE_CLAUDE_AGENT=true`), restart transport, call `POST /login/claude`, open the URL, then `launch` crews normally.
3. The startup `ConfigError` removal is non-breaking: operators who had `GA_CREW_ANTHROPIC_API_KEY` set will not notice.

## Context

Ghostship already supports two optional backends alongside kiro: Claude (added TRN-202) and Codex (added TRN-202). Both follow the same pattern:

1. A toolchain shell script (`crews/spec-ops/toolchains/<backend>.sh`) installs the ACP adapter package(s) at image build time.
2. `scripts/lib/agent_backends.sh` recognises the backend name in `GA_AGENT_BACKENDS`.
3. `transport/config.py` validates the backend name and provides login routes.
4. At crew launch, stored credentials are mounted into the crew container.

OpenCode follows the **Claude pattern** (login flow + stored credential file), not the Codex pattern (API key via env var):

- **Claude**: `opencode auth login` → `~/.local/share/opencode/auth.json` on the host → captured as `ga-opencode-auth` → mounted at crew launch. *(Analogous to `ga-claude-auth`)*
- **Codex**: `OPENAI_API_KEY` env var injected at launch — no login flow needed.

KiroCrew's `opencode.py` harness (verified from `src/kiro_crew/agent_sdk/host_auth.py`) reads credentials from `~/.local/share/opencode/auth.json`. KiroCrew handles injecting `OPENCODE_CONFIG_CONTENT` for permission routing — Ghostship does not need to set this. The install command is `npm install -g opencode-ai` (binary: `opencode`); there is no separate ACP adapter package.

See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- Add `opencode` as a valid `GA_AGENT_BACKENDS` name
- Install the `opencode-ai` npm package in the spec-ops image when enabled
- Provide a login flow to capture `ga-opencode-auth` credentials
- Mount credentials into the crew container at launch
- Add `POST /login/opencode` and `POST /logout/opencode` routes

**Non-goals:**
- API key injection via env var — OpenCode uses its own auth.json
- Making OpenCode the default backend
- Supporting opencode on the kiro-cli backend path

## Decisions

### Decision: Follow the Claude auth pattern, not the Codex pattern

OpenCode authenticates from `~/.local/share/opencode/auth.json` (written by `opencode auth login`). This is structurally identical to how Claude's `auth.json` works. Ghostship should reuse the login container + `ga-<backend>-auth` tarball mechanism already in place for Claude.

**Alternative considered:** Env-var API key (like Codex's `OPENAI_API_KEY`). OpenCode does support provider API keys in its config JSON, but KiroCrew's harness uses the `auth.json` credential file path and `opencode auth login` — matching this is simpler and correct.

### Decision: Use `npm install -g opencode-ai` directly (no ACP adapter)

Unlike Claude (which uses `@agentclientprotocol/claude-agent-acp`) and Codex (which uses `@agentclientprotocol/codex-acp`), OpenCode ships its own `opencode acp` subcommand in the main package. No separate ACP adapter needed.

### Decision: Pin a specific `opencode-ai` version in `opencode.sh`

Consistent with how `claude.sh` and `codex.sh` pin their packages. Find the version that KiroCrew's `packaging/kiro-cli-version` or `acp/harness/opencode.py` refers to for the installed 0.8.0 build, or pin the latest stable at the time of implementation.

## Risks / Trade-offs

- **Preview status** — OpenCode is upstream-preview in KiroCrew. The auth model or env wiring may change. Mitigation: document clearly; keep as opt-in only.
- **Login container scope** — the login container mechanism for Claude is already implemented. Reusing it for OpenCode should be straightforward, but needs testing that `opencode auth login` works inside a headless Podman container.
- **MCP server withheld** — KiroCrew withholds a whole MCP server from an OpenCode session if any of that server's tools is disabled. Test with full tool grants to confirm Ghostship's skill injection works.

## Migration Plan

No migration required. Entirely opt-in. Deployment: standard `./deploy.sh academy` after building a new spec-ops image.

## Open Questions

None — package name (`opencode-ai`), binary (`opencode`), and auth model (login flow + auth.json) confirmed from KiroCrew 0.8.0 source.

## Why

KiroCrew 0.7.0 shipped OpenCode as a selectable agent backend, removing the blocker that previously made TRN-168 infeasible. OpenCode is now a configuration task — the same pattern used to add Claude Code (TRN-202). Exposing it in Ghostship lets crews run agents on OpenCode alongside kiro-cli, Claude, and Codex.

## What Changes

- `GA_AGENT_BACKENDS` validation extended to accept `opencode` as a valid name alongside `kiro`, `claude`, and `codex`
- New toolchain script `crews/spec-ops/toolchains/opencode.sh` — installs the `opencode` binary, configures the provider API key via env var
- `scripts/install.sh` updated to handle `opencode` in `GA_AGENT_BACKENDS` (warn on inert settings, reject retired flags)
- `crews/spec-ops/Containerfile` updated to install opencode binary in the crew image when `opencode` is in `GA_AGENT_BACKENDS`
- `scripts/lib/agent_backends.sh` updated to recognise `opencode`
- `docs/configuration.md` updated with `opencode` backend documentation
- `docs/auth.md` updated for any API key / auth differences

OpenCode notes (from KiroCrew docs):
- Preview status in KiroCrew — requires Developer Mode on the gateway
- KiroCrew delivers Crew tools to OpenCode sessions, except it withholds a whole MCP server if any of that server's tools is disabled
- Compact is supported
- No per-turn steer, no slash commands on initial integration
- Auth is provider API keys via env vars — no browser flow

## Capabilities

### New Capabilities

- `opencode-backend`: OpenCode as a selectable Ghostship agent backend — toolchain, install, crew image, auth, env var wiring

### Modified Capabilities

- `agent-backends`: Extend `GA_AGENT_BACKENDS` valid names to include `opencode`; add inert-setting warnings for OpenCode credentials when disabled; extend install.sh validation

## Impact

- `scripts/lib/agent_backends.sh` — adds `opencode` to the valid set
- `scripts/install.sh` — extend backend handling
- `crews/spec-ops/Containerfile` — conditional opencode binary install
- `crews/spec-ops/toolchains/opencode.sh` — new file
- `transport/` — no changes expected (backend selection is a crew-image concern, not transport)
- `tests/unit/test_agent_backends.py` — add opencode coverage
- `docs/configuration.md`, `docs/auth.md` — documentation updates

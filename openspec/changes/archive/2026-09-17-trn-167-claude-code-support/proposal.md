## Why

KiroCrew 0.6.0 introduced Claude Code as an experimental selectable ACP backend (`acp_backend="claude"`), meaning the agent runtime inside each crew session can be switched from kiro-cli to Claude Code. Ghostship 0.5.x does not expose this capability: `_patch_crew_config` never sets `acp_backend`, crew images do not include `claude-agent-acp` or the `claude` CLI, and there is no mechanism to supply an Anthropic API key to a crew container. Adding Claude Code support gives operators a path to run ghostship crews on a different model provider and avoids hard dependency on kiro-cli availability.

## What Changes

- **New `GA_CREW_ACP_BACKEND` env var** — selects the ACP backend for newly launched crews (`"kiro"` (default) or `"claude"`). Setting this to `"claude"` enables Claude Code mode crew-wide.
- **New `GA_CREW_ANTHROPIC_API_KEY` env var** — the Anthropic API key injected into crew containers when Claude Code backend is selected.
- **Crew image layer** — `claude-agent-acp` npm package and the `claude` CLI are installed in the spec-ops Containerfile when Claude Code support is enabled; this is a build-time flag to keep the default image lean.
- **Secret injection** — `inject_auth.py` is extended with a Claude Code path: when `acp_backend=claude`, skip kiro-cli auth injection and instead inject `ANTHROPIC_API_KEY` from the transport's configured secret.
- **Lifecycle patching** — `_patch_crew_config` gains an `acp_backend` field write, wired to `GA_CREW_CREW_ACP_BACKEND` at `launch` time.
- **Network access note** — Claude Code calls `api.anthropic.com` directly from the crew container; a warning is emitted at launch if the backend is set to `claude`, noting the external network dependency.
- **Skill/persona/steering compatibility** — no changes required; existing persona prompts, skill injection, and steering files are compatible with Claude Code as confirmed by research.

## Capabilities

### New Capabilities

- `crew-acp-backend`: Configuration and runtime behavior for selecting the ACP agent backend (kiro-cli vs Claude Code) at crew launch time, including secret injection and capability flag enforcement.

### Modified Capabilities

- `crew-auth`: Auth injection currently assumes kiro-cli Builder ID / IAM Identity Center. The change adds a Claude Code path: when `acp_backend=claude`, inject `ANTHROPIC_API_KEY` env var instead of running the kiro-cli auth flow.
- `installation`: The spec-ops Containerfile and `install.sh` gain a conditional Claude Code layer (`claude-agent-acp`, `claude` CLI). Installation docs must document the new env vars and the Anthropic API key requirement.
- `crew-governance`: Tool approval handling changes for Claude Code: `dangerously_skip_permissions=True` bypasses KiroCrew's gate but not Claude Code's own approval layer. The governance spec must document this gap and the headless-stall risk, with a recommended mitigation (auto-accept mode configuration).

## Impact

- `academy/Containerfile` (spec-ops image) — new build layer for `claude-agent-acp` + `claude` CLI
- `transport/inject_auth.py` — new Claude Code branch
- `transport/lifecycle.py` (or equivalent `_patch_crew_config`) — `acp_backend` field write
- `transport/config.py` — two new env vars (`GA_CREW_ACP_BACKEND`, `GA_CREW_ANTHROPIC_API_KEY`)
- `install.sh` / setup docs — document new env vars
- Crew containers require outbound HTTPS to `api.anthropic.com` when Claude Code backend is active

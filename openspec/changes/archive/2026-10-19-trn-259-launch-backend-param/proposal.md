# Proposal

## Why

The transport can hold credentials for kiro, claude and codex at the same time, but every crew still launches on the one transport-wide default (`backends.default` → `GA_CREW_AGENT`, first entry). To run a kiro crew next to a claude crew, the Admiral has to change the default and reinstall. Multi-backend login is only useful if `launch` can pick the backend per crew.

## What Changes

- `launch` gains an optional `backend` parameter (`"kiro"`, `"claude"` or `"codex"`). When omitted, the crew uses the transport default exactly as today.
- The requested backend SHALL be an enabled backend (kiro always; claude/codex when listed in `backends.default`, since only those toolchains are baked into the crew image). Anything else returns an error naming the enabled backends and creates no container.
- Everything launch does per backend follows the crew's backend instead of the global default: credential lookup and the not-authenticated login flow, credential env injection at container create, post-start auth injection, `acp_backend` in the crew config, and the per-backend model override/default.
- The crew's backend is recorded in the registry (`acp_backend`, already present) and is the source of truth from then on. Reconcile/restart re-patches the crew config from the recorded backend, not the current default, so a crew never silently changes runtime when the default changes.
- The `launch` MCP tool description documents the parameter.

Out of scope: changing the backend of an existing crew, per-composition backend pinning, CLI or Captain support for choosing a backend, and changing which crews receive kiro auth on kiro login completion (claude/codex crews also bundle kiro-cli, so this stays as is).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `crew-acp-backend`: backend selection moves from transport-wide only to per-launch with the transport default as fallback; the registry-recorded backend drives restarts; per-backend credential requirements apply to the crew's backend.

## Impact

- `transport/tools.py`: `launch` signature, validation, auth gating and env injection keyed on the resolved backend.
- `transport/launcher.py` / `transport/lifecycle.py`: `finish_setup`, `_patch_crew_config`, `_patch_models` and the two restart paths take the crew's backend instead of reading `GA_CREW_ACP_BACKEND`.
- MCP tool schema for `launch` (additive, optional parameter; existing callers unaffected).
- Docs: `docs/` launch and backend pages; `ghostship-command` skill's launch guidance; `CHANGELOG.md`.
- Tests: unit coverage for each backend path and the restart behaviour.

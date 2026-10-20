# Proposal

## Why

Academy content (skills, steering, MCP catalogue) is only delivered to kiro-native paths inside crew containers. Claude and codex backend crews never receive it — agents operate without their skills, steering context, or MCP wiring, breaking Captain autopilot and OpenSpec workflows on non-kiro crews.

## What Changes

- **New**: `mcteamstar/.agents` is cloned into the crew image at build time (`/home/kirocrew/.agents`), providing the per-backend delivery path table and `setup` script.
- **New**: At crew launch, `AcademyLoader` populates the in-container `.agents/` staging directories (`.agents/skills/`, `.agents/context/`, `.agents/mcp/`) with manifest-selected academy content, then execs `.agents/setup <backend>` to wire everything to the backend's native harness paths.
- **Changed**: `AcademyLoader._copy_skills()`, `._copy_steering()`, and the MCP delivery in `._copy_agents()` are replaced by the `.agents`-mediated flow — ghostship no longer hardcodes per-backend destination paths.
- **Changed**: `crew-steering` capability: steering is no longer delivered exclusively to `~/.kiro/steering/`; it reaches the backend-appropriate path via `.agents/setup`.
- **Changed**: `mcp-server-config` capability: MCP catalogue is no longer delivered exclusively as `~/.kiro/mcp.json`; format and destination are backend-specific, handled by `.agents/setup`.
- **Unchanged**: Agent persona JSON delivery (`~/.kiro/agents/`) remains kiro-only — persona JSON is a kiro-specific concept with no claude/codex equivalent. MCP env-var substitution still runs at launch time since values require the runtime environment.
- **Unchanged**: Composition manifests, the academy content store, and install-time rsync into the data volume are unaffected.

## Capabilities

### New Capabilities

- `academy-backend-delivery`: Academy content (skills, steering, MCP) is delivered to the correct harness paths for the crew's backend (`kiro`, `claude`, `opencode`, `codex`) via `.agents/setup` at launch time. New backends require no ghostship changes — only an update to `mcteamstar/.agents`.

### Modified Capabilities

- `crew-steering`: Requirement that steering is delivered to `~/.kiro/steering/` changes — steering reaches the backend-native path (e.g. `~/.claude/rules/` for claude) via the `.agents`-mediated flow.
- `mcp-server-config`: Requirement that MCP catalogue is written as `~/.kiro/mcp.json` changes — delivery format and destination are now backend-specific.

## Impact

- `crews/spec-ops/Containerfile` (and any other composition Containerfiles): add `git clone mcteamstar/.agents /home/kirocrew/.agents` build step
- `transport/academy.py` (`AcademyLoader`): replace per-kind tar-inject methods with `.agents` staging + `setup <backend>` exec
- `transport/launcher.py`: pass `acp_backend` from registry to `AcademyLoader` at launch
- `mcteamstar/.agents`: must support running inside a container (real files not symlinks at install step is fine at bake time; any machine-specific detection that fails in container context needs hardening)
- No transport API changes, no compose.yml changes, no MCP tool signature changes

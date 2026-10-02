# TRN-186: Register Ghostship personas as KiroCrew crew members

## Problem

KiroCrew 0.7.0 tightened spawn security: `POST /api/spawn` now requires an
attested session identity (`X-Session-Token` verified against the gateway's
claim table). Headless agents calling `/api/spawn` via curl with only
`X-Internal-Secret` no longer pass attestation → `member_identity_unavailable`.

This breaks the entire Captain-driven workflow. Both `spec-driven-development`
and `independent-review` Captain orders instruct Raven to curl `/api/spawn`
directly. That worked on KiroCrew 0.6.0 but is intentionally blocked in 0.7.x
as part of the new session attestation security model.

## Root cause

Ghostship's agent personas are deployed as custom agent spec files in
`/agents/` but are **not registered as KiroCrew crew members** (`config.agents`
entries). Because they are not crew members:
- Raven runs as a headless session with no `member_session_key`
- Raven has no `KIROCREW_STUB_SESSION_TOKEN` in its environment
- Raven's `/api/spawn` calls fail attestation

## Proposed fix

Register all six Ghostship personas as named KiroCrew crew members in
`config.agents`. A named crew member:
1. Runs with `member_session_key` set → downstream `spawn_run` calls are attested
2. Has `KIROCREW_STUB_SESSION_TOKEN` published to its MCP server environment
3. Can call `spawn_run(agent="banshee", task="...")` to spawn other named members

Update order templates and Raven's prompt to use `spawn_run` MCP tool instead
of curl REST calls.

## Scope

### 1. Transport — `transport/lifecycle.py`
`_patch_crew_config` writes `config.agents` entries for all 6 personas into
`config.local.json`. Each entry specifies:
- `kiro_agent`: name matching the agent spec in `/agents/<name>.json`
- `memory_store`: `"default"` (shared crew store, personas don't need isolation)
- `model`: `""` (inherit from global `agent.model`)
- `session_control`: `true`
- `member_dispatch`: `true`

### 2. Order templates — `academy/orders/`
Both `spec-driven-development.md` and `independent-review.md` currently
instruct Raven to call `POST /api/spawn` via shell curl with `X-Internal-Secret`.
Replace with `spawn_run` MCP tool calls.

### 3. Raven agent spec — `academy/agents/raven.json`
Current prompt tells Raven to use the REST API directly for named persona
dispatch. Update to use `spawn_run` tool. Add `spawn_run` to Raven's
`allowedTools` list (it is a KiroCrew built-in tool).

### 4. Tests — `tests/unit/test_lifecycle.py`
Add tests asserting `_patch_crew_config` writes correct `config.agents`
entries for all 6 personas.

## What does NOT change
- The `dispatch` MCP tool on the transport (external spawns) — still works,
  still uses `POST /api/spawn`, but from the transport process which IS
  attested via a different path
- Agent prompt content (personality, capabilities) — only the spawn mechanism
  in Raven's prompt and the order templates changes
- The 6 agent spec files (other than Raven's `allowedTools`)

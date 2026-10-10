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

Two steps at crew launch time, plus updated Raven prompt and order templates:

**Step 1 — config.agents registration** (`_patch_crew_config`): write entries
for all 6 personas into `config.local.json`. This tells the gateway what
kiro_agent to use when a session opens on each member's slot.

**Step 2 — DM thread enrollment** (`_enroll_crew_members`): after gateway-ready,
call `POST /api/members/{slug}/thread` for each persona using the transport's
existing owner dashboard cookie. This creates the `dm.json` binding that causes
the gateway to stamp `KIROCREW_STUB_SESSION_TOKEN` into the session's MCP server
env when that member's slot is opened.

Once enrolled, Raven sessions have the token in their MCP env. `spawn_run` reads
it automatically and sends it as `X-Session-Token` — passing attestation. No
KiroCrew changes needed.

## Scope

### 1. Transport — `transport/lifecycle.py`
- `_patch_crew_config`: add `config.agents` entries for all 6 personas
- `_enroll_crew_members`: new function, calls `POST /api/members/{slug}/thread`
  for each persona via `_crew_api_with_recovery`; wired into all 3 callsites
  where `_patch_crew_config` runs and gateway-ready is confirmed

### 2. Order templates — `academy/orders/`
Replace all `POST /api/spawn` curl dispatch blocks in both
`spec-driven-development.md` and `independent-review.md` with `spawn_run` tool
call instructions. Keep intent-UUID idempotency pattern and all steer/status
REST calls unchanged.

### 3. Raven agent spec — `academy/agents/raven.json`
Add `spawn_run` to `allowedTools`. Replace curl-based dispatch instructions in
prompt with `spawn_run` tool call instructions. Keep all other content unchanged.

### 4. Tests — `tests/unit/test_lifecycle.py`
Tests for `_patch_crew_config` agents entries and `_enroll_crew_members`
endpoint calls and error handling.

## What does NOT change
- Transport cookie auth or dispatch mechanism
- Agent prompt content (personality, capabilities)
- The 5 non-Raven agent spec files
- KiroCrew itself (no fork changes)

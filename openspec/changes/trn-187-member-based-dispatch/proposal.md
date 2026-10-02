# TRN-187: Member-based dispatch — replace slot routing with member identity

## Why

The `slot` parameter on `dispatch()` was introduced to route tasks into named
dashboard sessions for browser visibility. KiroCrew 0.7.x introduced session
attestation: only sessions opened on an enrolled member DM slot carry an
attested `$KIRO_SESSION_ID`, enabling downstream `/api/spawn` calls. Generic
chat slots (`bridge`, UUID slots) have no attestation — agents dispatched
there cannot spawn other personas, silently breaking the Captain workflow.
TRN-186 added a targeted fix; TRN-187 makes the architecture coherent.

## What Changes

- **BREAKING** `slot` parameter semantics change for Ghostship persona agents:
  when no explicit slot is given, persona agents are dispatched into their
  enrolled member DM slot (`member-<slug>`) instead of `bridge` or headless.
  Explicit `slot` values are still respected but log a warning if they bypass
  attestation (e.g. `slot="bridge"`, `slot=True` for persona agents).
- **Remove** `_GHOSTSHIP_PERSONAS` hardcoded fallback — no backwards compatibility
  with pre-TRN-186 crews needed.
- **Simplify** slot naming: enrolled agents echo their agent name as the slot
  (e.g. `"ghost"`) not `"member-ghost"` — the `member-` prefix is an internal
  KiroCrew implementation detail, not user-facing.
- **Extend** member enrollment (`_enroll_crew_members`) to cover all agents in
  the composition manifest dynamically — not just the 6 hardcoded spec-ops personas.
- **Update** `dispatch()` MCP tool documentation: clarify that persona agents
  always route via member slots; `slot` controls only non-persona or explicit
  overrides.
- **Update** `_GHOSTSHIP_PERSONAS` to be derived from the active crew's enrolled
  members at dispatch time rather than a hardcoded module-level frozenset, so
  custom compositions work without code changes.

## Capabilities

### Modified Capabilities
- `batch-dispatch` — dispatch slot routing logic changes; member slot auto-route
  replaces bridge default for enrolled agents
- `task-orchestration` — session identity contract changes: all persona
  dispatches now guarantee an attested session
- `agent-personas` — persona dispatch contract: agents are always enrolled as
  crew members, always attested

### New Capabilities
- `crew-member-enrollment` — new capability: at crew launch, all composition
  agents are enrolled as named KiroCrew crew members via
  `POST /api/members/{slug}/thread`; enrollment is idempotent and composition-aware

## Impact

- `transport/server.py` — `dispatch()` slot resolution and parent_session injection
- `transport/lifecycle.py` — `_dispatch_tasks()`, `_enroll_crew_members()`,
  `_GHOSTSHIP_PERSONAS`, `_patch_crew_config()` agents dict
- `transport/` tests — slot routing tests need updating
- Ghostship MCP tool docs (`dispatch` tool description) — `slot` param semantics
- No changes to KiroCrew, order templates, or agent specs

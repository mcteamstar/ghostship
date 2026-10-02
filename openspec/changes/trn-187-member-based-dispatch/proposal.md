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
  with pre-TRN-186 crews needed. Any crew without `enrolled_agents` in the
  registry gets bridge/headless for all agents.
- **Simplify** slot naming: enrolled agents echo their agent name as the slot
  (e.g. `"ghost"`) not `"member-ghost"` — the `member-` prefix is a KiroCrew
  internal detail, not user-facing.
- **Extend** member enrollment (`_enroll_crew_members`) to cover all agents in
  the composition manifest dynamically — not just a hardcoded list.
- **Update** `dispatch()` MCP tool documentation: enrolled agents default to
  their agent name as slot (attested member DM slot); explicit slot bypasses
  attestation with a warning.

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

- `transport/server.py` — `dispatch()` uses `_resolve_dispatch_slot()`; slot docstring updated; `_GHOSTSHIP_PERSONAS` import removed
- `transport/lifecycle.py` — `enrolled_agents` persisted in registry; `_resolve_dispatch_slot()` helper; `_dispatch_batch()` simplified; `_GHOSTSHIP_PERSONAS` removed from routing
- `transport/` tests — fixtures get `enrolled_agents`; slot assertions updated for agent-name echo
- `.claude-plugin/skills/ghostship-command/SKILL.md` — slot param description updated
- No changes to KiroCrew, order templates, or agent specs

# Design: TRN-187 Member-based dispatch

## Context

TRN-186 landed three targeted fixes:
1. `config.agents` entries written at `_patch_crew_config`
2. `_enroll_crew_members()` calling `POST /api/members/{slug}/thread` after gateway-ready
3. `_GHOSTSHIP_PERSONAS` frozenset used in slot resolution to auto-route to `member-<slug>`

Rough edges to clean up:
- `_GHOSTSHIP_PERSONAS` hardcoded — custom compositions silently skip member routing
- Slot resolution duplicated in `server.py` (single dispatch) and `lifecycle.py` (batch)
- Slot echoed as `"member-ghost"` — `member-` is a KiroCrew internal prefix, not user-facing
- `slot` docstring outdated

## Approach

### 1. enrolled_agents in crew registry

At launch (fresh + all recovery paths), after `_enroll_crew_members()`, write
the enrolled slugs into the crew registry entry:

```python
"enrolled_agents": [n.removesuffix(".json") for n in copied_agents]
```

At dispatch time, `_resolve_dispatch_slot` reads `crew.get("enrolled_agents")`.
No hardcoded fallback — any crew without `enrolled_agents` gets bridge/headless
(which is the pre-TRN-186 behaviour anyway, no regression).

### 2. _resolve_dispatch_slot — unified helper

Single function used by both `server.py` `dispatch()` and `lifecycle.py`
`_dispatch_batch()`:

```python
def _resolve_dispatch_slot(agent, slot, crew):
    enrolled = frozenset(crew.get("enrolled_agents") or [])
    if slot is None and agent in enrolled:
        return agent, f"dashboard:member-{agent}"   # echo agent name, internal uses member-
    if slot is None:
        return ("bridge", "dashboard:bridge") if crew.get("dashboard_port") else (None, None)
    if slot is True:
        slug = uuid.uuid4().hex[:8]
        return True, f"dashboard:{slug}"
    return slot, f"dashboard:{slot}"
```

**Naming:** echoed slot is the agent name (`"ghost"`, `"raven"`) not
`"member-ghost"`. The `member-` prefix is KiroCrew's internal DM slot key prefix
— the Admiral doesn't need to know about it. The `parent_session` sent to the
gateway still uses `"dashboard:member-<slug>"` as required by KiroCrew.

Explicit slots (`"bridge"`, `slot=True`, any string) are honoured as-is.
A warning is logged when an enrolled agent's attestation is bypassed.

### 3. No backwards compatibility

`_GHOSTSHIP_PERSONAS` removed from dispatch routing entirely. Kept only as a
module-level constant for reference (documents the spec-ops default set). Crews
launched before TRN-186 have no `enrolled_agents` in registry → get
bridge/headless for all agents → no attestation, same as before TRN-186.

### 4. Files changed

- `transport/lifecycle.py` — `enrolled_agents` in registry; `_resolve_dispatch_slot()`; updated `_dispatch_batch()`; remove `_GHOSTSHIP_PERSONAS` from routing logic
- `transport/server.py` — updated `dispatch()` to use helper; remove `_GHOSTSHIP_PERSONAS` import; updated docstring
- `tests/unit/test_dispatch_slot.py` — fixtures get `enrolled_agents`; assertions updated for new slot naming
- `tests/unit/test_server.py` — fixture gets `enrolled_agents`; assertion updated
- `.claude-plugin/skills/ghostship-command/SKILL.md` — slot param description updated

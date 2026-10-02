# Design: TRN-187 Member-based dispatch

## Context

TRN-186 landed three targeted fixes:
1. `config.agents` entries for 6 hardcoded personas at `_patch_crew_config`
2. `_enroll_crew_members()` calling `POST /api/members/{slug}/thread` after gateway-ready
3. `_GHOSTSHIP_PERSONAS` frozenset used in slot resolution to auto-route to `member-<slug>`

The current state has three rough edges:
- `_GHOSTSHIP_PERSONAS` is a hardcoded frozenset — custom compositions break silently
- The fix is in `server.py` (single dispatch) and `lifecycle.py` (batch dispatch) separately — duplication
- `slot=True` and explicit `slot="bridge"` still bypass member routing for personas
- The `slot` parameter's new semantics aren't documented

## Approach

### 1. Dynamic enrolled-agents registry per crew

At launch, after `_enroll_crew_members()` succeeds, persist the set of enrolled
agent slugs in the crew's registry entry:

```python
# In _finish_crew_setup, after _enroll_crew_members:
with _registry_lock:
    reg = _load_registry()
    reg["crews"][crew_id]["enrolled_agents"] = [
        n.removesuffix(".json") for n in copied_agents
    ]
    _save_registry(reg)
```

At dispatch time, check `crew.get("enrolled_agents", [])` instead of
`_GHOSTSHIP_PERSONAS`. This makes routing correct for any composition.

Keep `_GHOSTSHIP_PERSONAS` as a fallback for crews launched before TRN-187
(backward compatibility — crews without `enrolled_agents` in registry).

### 2. Unify slot resolution

Extract a shared `_resolve_dispatch_slot(agent, slot, crew)` helper used by
both `server.py` `dispatch()` and `lifecycle.py` `_dispatch_tasks()`:

```python
def _resolve_dispatch_slot(
    agent: str, slot: str | bool | None, crew: dict
) -> tuple[str | bool | None, str | None]:
    """Return (effective_slot, parent_session).

    For enrolled persona agents with no explicit slot: routes to member-<slug>.
    For other agents with no explicit slot: bridge if dashboard, else None.
    Explicit slot always respected.
    """
    enrolled = set(crew.get("enrolled_agents", [])) or _GHOSTSHIP_PERSONAS
    if slot is None and agent in enrolled:
        return None, f"dashboard:member-{agent}"
    if slot is None:
        if crew.get("dashboard_port"):
            return "bridge", "dashboard:bridge"
        return None, None
    if slot is True:
        slug = uuid.uuid4().hex[:8]
        return True, f"dashboard:{slug}"
    return slot, f"dashboard:{slot}"
```

### 3. slot=True and slot="bridge" for persona agents

When an explicit `slot="bridge"` or `slot=True` is passed for a persona agent,
honour it (the caller opted in) but log a warning that attestation may be
unavailable. Don't silently override explicit caller intent.

### 4. dispatch() tool description update

Update the `slot` parameter description in the `dispatch()` MCP tool to document:
- Persona agents default to their member DM slot (attested)
- `slot="bridge"` still accepted but not attested for persona agents
- `slot="member-<slug>"` is equivalent to the default for enrolled agents

## Files to change

- `transport/lifecycle.py` — add `enrolled_agents` to registry at launch; add
  `_resolve_dispatch_slot()`; update `_dispatch_tasks()` to use it
- `transport/server.py` — update `dispatch()` to use `_resolve_dispatch_slot()`;
  update `slot` param docstring
- `tests/unit/test_lifecycle.py` — update slot routing tests
- `tests/unit/test_server.py` (if exists) — update dispatch slot tests

## Migration

Existing crews in the registry have no `enrolled_agents` key. The fallback to
`_GHOSTSHIP_PERSONAS` handles this. On next restart/recovery `_enroll_crew_members`
re-runs and the key gets written.

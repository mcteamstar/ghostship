# TRN-192 — Simplify dispatch slot model

## Why

The `slot` parameter on `dispatch()` supports four modes: `None` (headless),
`True` (UUID slot), `"bridge"` (shared slot), and `"name"` (named slot). With
member-based dispatch (TRN-186/187) working correctly, only two of these make
sense:

**Empirical findings (2026-10-03, academy):**

| Mode | RSS delta | Attested | Visible in UI |
|:-----|:----------|:---------|:--------------|
| Headless (`slot=None`) | +46 MB | ✅ via member enrollment | No |
| Member slot (default) | +294 MB | ✅ | Yes (member thread) |
| Named/UUID slot | +294 MB | ❌ | Yes (own session) |

Named slots and `slot=True` cost the same memory as member slots but are **not
attested** — agents dispatched into them cannot spawn sub-agents. Member slots
already provide browser visibility for free. Named/UUID slots offer no
advantage over member slots and break orchestration.

## What Changes

**Remove:**
- `slot=True` — UUID auto-generation path in `_resolve_dispatch_slot`
- `slot="name"` — arbitrary string named slots
- `slot="bridge"` — pre-enrollment legacy shared slot

**Keep:**
- `slot=None` — headless, no session, attested, saves ~250 MB vs slotted
- Default (omit slot) — routes enrolled agents to `member-{agent}`, attested,
  dashboard-visible

**New `slot` semantics:**

```python
dispatch(agent="ghost")          # → member-ghost slot (attested, visible)
dispatch(agent="ghost", slot=None) # → headless (attested, no session, -250 MB)
```

The `slot` parameter on the MCP tool becomes `slot: bool | None`:
- `None` (default) → member slot (enrolled agents) or headless (unenrolled)
- `False` → explicit headless regardless of enrollment

## Scope

- `transport/lifecycle.py` — `_resolve_dispatch_slot`: remove UUID, named, and
  bridge paths
- `transport/server.py` — `dispatch()` tool: simplify `slot` param, update
  docstring
- `tests/unit/test_dispatch_slot.py` — remove UUID/named/bridge test cases
- `README.md` — update `dispatch` tool slot documentation
- `.claude-plugin/skills/ghostship-command/SKILL.md` — update slot guidance

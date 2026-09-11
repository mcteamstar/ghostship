## Context

See proposal.md — Why.

TRN-133 shipped `mode: "headless" | "anchored" | "free"`. This replaces that with `slot: str | bool | None`. The underlying mechanism is identical — `POST /api/chat/slots` + `parent_session` on `/api/spawn` — the abstraction changes, not the implementation.

## Goals / Non-Goals

**Goals:**
- Replace `mode` with `slot` in `dispatch()` and `_dispatch_batch()`
- Support `slot=None`, `slot=True`, `slot="<name>"` with the semantics defined in the spec
- Default to `"bridge"` when `dashboard_port` is set, `None` otherwise
- Echo resolved slot in response
- Update tests and docstring

**Non-Goals:**
- Changing the underlying `/api/chat/slots` + `parent_session` mechanism
- Adding slot management tools (list, delete, rename slots)
- Applying slot to `schedule()` or Captain cron sessions

## Decisions

**D1 — `slot` type is `str | bool | None`**
`True` is the signal for "auto-generate a unique name". A string is a literal slot name. `None` is headless. This avoids a magic string like `"auto"` and makes the intent unambiguous in Python.

**D2 — Default slot name is `"bridge"`**
When dashboard is active and no explicit slot is provided, default to the literal string `"bridge"`. This is a well-known shared session name — the crew's command post. No per-crew suffix needed; `"bridge"` is the same on every crew.

**D3 — Breaking change: remove `mode`**
`mode` is removed entirely rather than keeping it as a deprecated alias. TRN-133 just shipped and no external callers are pinned to it yet. Clean break is better than maintaining two parameters with overlapping semantics.

**D4 — `slot=True` generates suffix only (no crew-id prefix)**
For `slot=True`, generate `uuid4().hex[:8]` as the full slot name (no crew-id prefix). The slot name doesn't need to carry crew identity — it's scoped to the crew's gateway already.

**D5 — Slot pre-creation is non-fatal**
`POST /api/chat/slots` failures (including 409) are silently ignored — the `parent_session` routing still works via the `dashboard:` prefix mechanism even if slot creation fails.

## Implementation Plan

### 1. `transport/server.py` — `dispatch()`

Replace `mode: str | None = None` with `slot: str | bool | None = None`.

Resolve effective slot:
```python
if slot is None:
    effective_slot = "bridge" if crew.get("dashboard_port") else None
else:
    effective_slot = slot  # True or str
```

Build parent_session and pre-create slot:
```python
parent_session: str | None = None
if effective_slot is True:
    slot_name = uuid.uuid4().hex[:8]
    parent_session = f"dashboard:{slot_name}"
    try:
        _crew_api(crew, "POST", "/api/chat/slots", json={"name": slot_name})
    except Exception:
        pass
elif isinstance(effective_slot, str):
    parent_session = f"dashboard:{effective_slot}"
    try:
        _crew_api(crew, "POST", "/api/chat/slots", json={"name": effective_slot})
    except Exception:
        pass

if parent_session:
    body["parent_session"] = parent_session
```

Response: replace `"mode": effective_mode` with `"slot": slot_name if slot=True else effective_slot`.

### 2. `transport/lifecycle.py` — `_dispatch_batch()`

Same replacement. For `slot=True` in batch: generate a distinct suffix per task.

### 3. `transport/server.py` — docstring

Update dispatch() docstring to document `slot` parameter, remove `mode` references.

### 4. Tests

Rewrite `tests/unit/test_dispatch_modes.py` → `tests/unit/test_dispatch_slot.py`:
- `slot=None` → no parent_session
- `slot="bridge"` → parent_session="dashboard:bridge"
- `slot=True` → parent_session matches `dashboard:[0-9a-f]{8}`
- Two `slot=True` calls → distinct parent_session values
- `slot="custom"` → parent_session="dashboard:custom"
- No slot + dashboard_port set → defaults to "bridge"
- No slot + no dashboard_port → defaults to None (headless)
- Batch with `slot=True` → each task gets distinct slot
- Batch with `slot="shared"` → all tasks get same slot

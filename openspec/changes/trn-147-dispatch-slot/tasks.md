## 1. dispatch() — replace mode with slot

- [ ] 1.1 Remove `mode: str | None = None` parameter from `dispatch()` in `transport/server.py`
- [ ] 1.2 Add `slot: str | bool | None = None` parameter
- [ ] 1.3 Replace effective mode resolution with slot resolution: `"bridge"` if `crew.get("dashboard_port")` and slot is None, else slot
- [ ] 1.4 For `slot=True`: generate `uuid.uuid4().hex[:8]` as slot name, set `parent_session = f"dashboard:{slot_name}"`, call `POST /api/chat/slots {"name": slot_name}` (non-fatal)
- [ ] 1.5 For `slot="<name>"`: set `parent_session = f"dashboard:{slot}"`, call `POST /api/chat/slots {"name": slot}` (409 ok, non-fatal)
- [ ] 1.6 For `slot=None` (resolved): no `parent_session`, no slot creation
- [ ] 1.7 Replace `"mode": effective_mode` in response with `"slot": <resolved-slot-name-or-null>` — for `slot=True` echo the generated name, for string echo the string, for None echo null
- [ ] 1.8 Update `dispatch()` docstring: document `slot` parameter, remove all `mode` references

## 2. _dispatch_batch() — replace mode with slot

- [ ] 2.1 Remove `mode` parameter from `_dispatch_batch()` in `transport/lifecycle.py`, add `slot: str | bool | None = None`
- [ ] 2.2 Apply same slot resolution logic as dispatch()
- [ ] 2.3 For `slot=True` in batch loop: generate a distinct `uuid.uuid4().hex[:8]` suffix per task, pre-create slot, set per-task `parent_session`
- [ ] 2.4 For string slot in batch: pre-create slot once (before the loop), set same `parent_session` for all tasks
- [ ] 2.5 Replace `"mode"` in batch response with `"slot"`; for `slot=True` include `"task_slots"` dict mapping task_id → slot name

## 3. Tests

- [ ] 3.1 Rename `tests/unit/test_dispatch_modes.py` → `tests/unit/test_dispatch_slot.py` and rewrite for slot parameter
- [ ] 3.2 Unit: `slot=None` — no `parent_session` in body, response has `"slot": null`
- [ ] 3.3 Unit: `slot="bridge"` — body has `parent_session="dashboard:bridge"`, response has `"slot": "bridge"`
- [ ] 3.4 Unit: `slot=True` — body has `parent_session` matching `^dashboard:[0-9a-f]{8}$`, response has `"slot"` with that name
- [ ] 3.5 Unit: two `slot=True` dispatches → distinct `parent_session` values
- [ ] 3.6 Unit: `slot="custom-name"` — `parent_session="dashboard:custom-name"`
- [ ] 3.7 Unit: no explicit slot + crew has `dashboard_port` → effective slot is `"bridge"`
- [ ] 3.8 Unit: no explicit slot + no `dashboard_port` → effective slot is null (headless)
- [ ] 3.9 Unit: batch with `slot=True` → each task gets a distinct `parent_session`
- [ ] 3.10 Unit: batch with `slot="shared"` → all tasks get `parent_session="dashboard:shared"`
- [ ] 3.11 Run full unit suite — all tests pass

## 4. Verification

- [ ] 4.1 `python3 -m py_compile transport/server.py transport/lifecycle.py` — syntax clean
- [ ] 4.2 Deploy to vm23 and dispatch with no explicit slot on a dashboard crew — confirm `"slot": "bridge"` in response and session appears in dashboard Sessions list
- [ ] 4.3 Dispatch with `slot="my-test"` — confirm named slot appears in Sessions list
- [ ] 4.4 Dispatch with `slot=True` — confirm unique slot appears in Sessions list

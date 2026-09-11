## 1. dispatch() — add mode parameter

- [ ] 1.1 Add `mode: str | None = None` parameter to `dispatch()` in `transport/server.py`
- [ ] 1.2 After the existing model/agent validation, resolve effective mode: use explicit `mode` if provided, else derive from `crew.get("dashboard_url")` — `"anchored"` if set, `"headless"` otherwise
- [ ] 1.3 Validate effective mode is one of `"headless"`, `"anchored"`, `"free"` — return an error before any spawn call if invalid
- [ ] 1.4 For `anchored` mode: add `parent_session = f"dashboard:{crew_id}"` to the `/api/spawn` body
- [ ] 1.5 For `free` mode: generate a transport-side `uuid.uuid4().hex[:8]` suffix before the spawn call; add `parent_session = f"dashboard:{crew_id}-{suffix}"` to the body
- [ ] 1.6 Include `"mode"` in the `dispatch()` response dict; for `free` mode also include `"parent_session"` so the caller knows which slot to watch
- [ ] 1.7 Update the `dispatch()` docstring to document `mode` and its three values

## 2. _dispatch_batch() — propagate mode

- [ ] 2.1 Add `mode` parameter to `_dispatch_batch()` and pass it through from `dispatch()`
- [ ] 2.2 Resolve the effective mode inside `_dispatch_batch()` using the same live-lookup logic (`dashboard_url` check)
- [ ] 2.3 For `anchored` mode: add the same `parent_session = f"dashboard:{crew_id}"` to every task's spawn body
- [ ] 2.4 For `free` mode: generate a distinct UUID suffix per task in the batch loop
- [ ] 2.5 Include `"mode"` at the top level of the batch response; include per-task `"parent_session"` entries for `free` mode

## 3. Tests

- [ ] 3.1 Unit: `mode="headless"` — `/api/spawn` body has no `parent_session`
- [ ] 3.2 Unit: `mode="anchored"` — body has `parent_session="dashboard:<crew-id>"`
- [ ] 3.3 Unit: `mode="free"` — body has `parent_session` matching `dashboard:<crew-id>-<8hex>` and response includes `parent_session`
- [ ] 3.4 Unit: two `dispatch` calls with `free` mode produce different `parent_session` values
- [ ] 3.5 Unit: invalid `mode` returns error, no spawn call made
- [ ] 3.6 Unit: crew with `dashboard_url` set, no explicit `mode` → effective mode is `anchored`
- [ ] 3.7 Unit: crew with no `dashboard_url`, no explicit `mode` → effective mode is `headless`
- [ ] 3.8 Unit: batch with `mode="free"` — each task gets a distinct `parent_session`
- [ ] 3.9 Unit: batch with `mode="anchored"` — all tasks get the same `parent_session`
- [ ] 3.10 Run full unit suite — all tests pass

## 4. Verification

- [ ] 4.1 `python3 -m py_compile transport/server.py` — syntax clean
- [ ] 4.2 Launch a crew with `dashboard=False`, dispatch with no explicit mode — confirm `mode: headless` in response and no `parent_session` in spawn body
- [ ] 4.3 Launch a crew with `dashboard=True`, dispatch with no explicit mode — confirm `mode: anchored` in response

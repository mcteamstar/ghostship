## 1. Registry — store mode_default at launch

- [x] 1.1 In `transport/lifecycle.py` `_finish_crew_setup()`, add `"mode_default": "anchored" if dashboard else "headless"` to the registry entry written for the new crew
- [x] 1.2 In `transport/lifecycle.py` `_reconcile_registry()`, backfill `mode_default` for existing registry entries that lack it (default to `"headless"`)

## 2. dispatch() — add mode parameter

- [x] 2.1 Add `mode: str | None = None` parameter to `dispatch()` in `transport/server.py`
- [x] 2.2 After the existing model/agent validation, resolve effective mode: use explicit `mode` if provided, else read `crew.get("mode_default", "headless")` from the registry entry
- [x] 2.3 Validate effective mode is one of `"headless"`, `"anchored"`, `"free"` — return an error before any spawn call if invalid
- [x] 2.4 For `shared` mode: add `parent_session = f"dashboard:{crew_id}"` to the `/api/spawn` body
- [x] 2.5 For `unique` mode: generate a transport-side `uuid.uuid4().hex[:8]` suffix before the spawn call; add `parent_session = f"dashboard:{crew_id}-{suffix}"` to the body
- [x] 2.6 Include `"mode"` in the `dispatch()` response dict; for `unique` mode also include `"parent_session"` so the caller knows which slot to watch
- [x] 2.7 Update the `dispatch()` docstring to document `mode` and its three values

## 3. _dispatch_batch() — propagate mode

- [x] 3.1 Add `mode` parameter to `_dispatch_batch()` and pass it through from `dispatch()`
- [x] 3.2 Resolve the effective mode inside `_dispatch_batch()` using the same logic as `dispatch()` (explicit > registry default)
- [x] 3.3 For `shared` mode: add the same `parent_session = f"dashboard:{crew_id}"` to every task's spawn body
- [x] 3.4 For `unique` mode: generate a distinct UUID suffix per task in the batch loop
- [x] 3.5 Include `"mode"` at the top level of the batch response; include per-task `"parent_session"` entries for `unique` mode

## 4. Tests

- [x] 4.1 Unit: `mode="headless"` — `/api/spawn` body has no `parent_session`
- [x] 4.2 Unit: `mode="anchored"` — body has `parent_session="dashboard:<crew-id>"`
- [x] 4.3 Unit: `mode="free"` — body has `parent_session` matching `dashboard:<crew-id>-<8hex>` and response includes `parent_session`
- [x] 4.4 Unit: two `dispatch` calls with `unique` mode produce different `parent_session` values
- [x] 4.5 Unit: invalid `mode` returns error, no spawn call made
- [x] 4.6 Unit: no explicit `mode`, crew registry has `mode_default="anchored"` → effective mode is `shared`
- [x] 4.7 Unit: no explicit `mode`, crew registry has `mode_default="headless"` → effective mode is `none`
- [x] 4.8 Unit: batch with `mode="free"` — each task gets a distinct `parent_session`
- [x] 4.9 Unit: batch with `mode="anchored"` — all tasks get the same `parent_session`
- [x] 4.10 Run full unit suite — all tests pass

## 5. Verification

- [x] 5.1 `python3 -m py_compile transport/server.py transport/lifecycle.py` — syntax clean
- [x] 5.2 Launch a crew with `dashboard=False`, dispatch with no explicit mode — confirm `mode: none` in response and no `parent_session` in spawn body (via test or manual probe)
- [x] 5.3 Launch a crew with `dashboard=True`, dispatch with no explicit mode — confirm `mode: shared` in response

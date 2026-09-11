## 1. Registry — store dispatch_mode_default at launch

- [ ] 1.1 In `transport/lifecycle.py` `_finish_crew_setup()`, add `"dispatch_mode_default": "shared" if dashboard else "none"` to the registry entry written for the new crew
- [ ] 1.2 In `transport/lifecycle.py` `_reconcile_registry()`, backfill `dispatch_mode_default` for existing registry entries that lack it (default to `"none"`)

## 2. dispatch() — add dispatch_mode parameter

- [ ] 2.1 Add `dispatch_mode: str | None = None` parameter to `dispatch()` in `transport/server.py`
- [ ] 2.2 After the existing model/agent validation, resolve effective mode: use explicit `dispatch_mode` if provided, else read `crew.get("dispatch_mode_default", "none")` from the registry entry
- [ ] 2.3 Validate effective mode is one of `"none"`, `"shared"`, `"unique"` — return an error before any spawn call if invalid
- [ ] 2.4 For `shared` mode: add `parent_session = f"dashboard:{crew_id}"` to the `/api/spawn` body
- [ ] 2.5 For `unique` mode: generate a transport-side `uuid.uuid4().hex[:8]` suffix before the spawn call; add `parent_session = f"dashboard:{crew_id}-{suffix}"` to the body
- [ ] 2.6 Include `"dispatch_mode"` in the `dispatch()` response dict; for `unique` mode also include `"parent_session"` so the caller knows which slot to watch
- [ ] 2.7 Update the `dispatch()` docstring to document `dispatch_mode` and its three values

## 3. _dispatch_batch() — propagate dispatch_mode

- [ ] 3.1 Add `dispatch_mode` parameter to `_dispatch_batch()` and pass it through from `dispatch()`
- [ ] 3.2 Resolve the effective mode inside `_dispatch_batch()` using the same logic as `dispatch()` (explicit > registry default)
- [ ] 3.3 For `shared` mode: add the same `parent_session = f"dashboard:{crew_id}"` to every task's spawn body
- [ ] 3.4 For `unique` mode: generate a distinct UUID suffix per task in the batch loop
- [ ] 3.5 Include `"dispatch_mode"` at the top level of the batch response; include per-task `"parent_session"` entries for `unique` mode

## 4. Tests

- [ ] 4.1 Unit: `dispatch_mode="none"` — `/api/spawn` body has no `parent_session`
- [ ] 4.2 Unit: `dispatch_mode="shared"` — body has `parent_session="dashboard:<crew-id>"`
- [ ] 4.3 Unit: `dispatch_mode="unique"` — body has `parent_session` matching `dashboard:<crew-id>-<8hex>` and response includes `parent_session`
- [ ] 4.4 Unit: two `dispatch` calls with `unique` mode produce different `parent_session` values
- [ ] 4.5 Unit: invalid `dispatch_mode` returns error, no spawn call made
- [ ] 4.6 Unit: no explicit `dispatch_mode`, crew registry has `dispatch_mode_default="shared"` → effective mode is `shared`
- [ ] 4.7 Unit: no explicit `dispatch_mode`, crew registry has `dispatch_mode_default="none"` → effective mode is `none`
- [ ] 4.8 Unit: batch with `dispatch_mode="unique"` — each task gets a distinct `parent_session`
- [ ] 4.9 Unit: batch with `dispatch_mode="shared"` — all tasks get the same `parent_session`
- [ ] 4.10 Run full unit suite — all tests pass

## 5. Verification

- [ ] 5.1 `python3 -m py_compile transport/server.py transport/lifecycle.py` — syntax clean
- [ ] 5.2 Launch a crew with `dashboard=False`, dispatch with no explicit mode — confirm `dispatch_mode: none` in response and no `parent_session` in spawn body (via test or manual probe)
- [ ] 5.3 Launch a crew with `dashboard=True`, dispatch with no explicit mode — confirm `dispatch_mode: shared` in response

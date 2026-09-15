# Design: TRN-157 — Generation-Counter Race + Admiral Keypair TOCTOU

## Context

See `proposal.md — Why` for motivation.

### CR-1: The three-caller window in `_ensure_crew_running`

`_ensure_crew_running` in `transport/lifecycle.py` uses a per-crew `threading.Event` to serialise concurrent restarts. The TRN-152 fix ensures waiters read `_crew_restart_outcomes` after `event.wait()` returns. However there is a window:

```
Thread A (leader):  ...restart work...  →  _crew_restart_outcomes[id] = outcome
                                        →  _startup_events.pop(id)        ← event entry removed
                                        →  event.set()                    ← waiters wake
Thread B (waiter):  woke from event.wait()
                                        [B has not read the outcome yet]
Thread C (arrives): sees _startup_events[id] is missing → becomes NEW leader
                    → _crew_restart_outcomes.pop(id, None)               ← CLEARS B's outcome
Thread B:           reads _crew_restart_outcomes.get(id) → None → raises spurious error
```

The window is between `_startup_events.pop(id)` (line 761) and `event.set()` (line 762), which is a single GIL-interleaving step; in practice the window is between `event.set()` and waiter B's read at line 622.

### CR-2: Missing `_cleanup_crew` call on cookie-mint failure in `_finish_crew_setup`

`_finish_crew_setup` calls `_cleanup_crew` on the two gateway-timeout error-dict returns (lines ~1719, ~1747–1748) but not on the cookie-mint failure return at line ~1790:

```python
cookie = _mint_cookie(podman, container, crew_url)
if not cookie:
    _cleanup_crew(podman, container, volume, home_volume)   # ← MISSING before TRN-157
    return {"error": f"Failed to mint session cookie for crew {crew_id}"}
```

When this path fires, `secret_create("admiral-pubkey-{crew_id}")` has already succeeded (it ran before `container_create`, which ran before the first `_wait_gateway`). Without the `_cleanup_crew` call, the secret persists in Podman's global namespace. A subsequent `launch()` with the same `crew_id` will fail at `secret_create` with a 409.

Lock state at the cookie-mint failure: the registry has already been written under `_registry_lock` to record the crew as "running" (line ~1802). This means the cleanup path must also remove the registry entry — which `_cleanup_crew` does NOT do. The `launch()` outer `except` block cleans the registry (line ~2114), but on the error-dict return path the exception is swallowed inside `_finish_crew_setup`. This needs a two-part fix:

1. Add `_cleanup_crew` before the cookie-mint failure return inside `_finish_crew_setup`.
2. Add registry cleanup at the `launch()` call site when `_finish_crew_setup` returns an error dict.

## Goals / Non-Goals

**Goals:**
- Prevent spurious RuntimeError for the third concurrent waiter in `_ensure_crew_running`
- Ensure `admiral-pubkey-{crew_id}` is removed on every failed `launch()` path
- Ensure the registry entry is also cleaned up when `_finish_crew_setup` returns an error dict

**Non-Goals:**
- Retrying the restart automatically when the generation changes (raising is correct; the caller can retry if appropriate)
- Changing the two-caller TRN-152 behavior
- Changing the `_finish_crew_setup` function signature

## Decisions

### D1: Generation counter stored alongside `_startup_events`

**Design**:
```python
_startup_generation: dict[str, int] = {}  # guarded by _startup_events_lock
```

Increment on leader election (inside the existing `_startup_events_lock` block):
```python
with _startup_events_lock:
    if crew_id in _startup_events:
        event = _startup_events[crew_id]
        is_leader = False
        gen = _startup_generation.get(crew_id, 0)  # waiter captures current gen
    else:
        event = threading.Event()
        _startup_events[crew_id] = event
        is_leader = True
        _crew_restart_outcomes.pop(crew_id, None)
        _startup_generation[crew_id] = _startup_generation.get(crew_id, 0) + 1
        gen = _startup_generation[crew_id]
```

Waiter, after `event.wait()`:
```python
event.wait(timeout=45)
with _startup_events_lock:
    outcome = _crew_restart_outcomes.get(crew_id)
    current_gen = _startup_generation.get(crew_id, 0)
if current_gen != gen:
    raise RuntimeError(
        f"Crew {crew_id} restart (concurrent) failed -- restart cycle changed during wait "
        f"(gen {gen} → {current_gen}); the new leader may have succeeded or failed"
    )
# ... existing outcome-read logic ...
```

The leader's `finally` block pops `_startup_events[crew_id]` as before. The generation counter is NOT popped — it persists until the next election, where it is incremented again.

**Alternatives considered**:
- **Re-acquire lock and check `_startup_events[crew_id]` exists**: If the dict has the key again (new leader), generation has changed. But this is racy — the new leader may not have written the key yet when the waiter checks.
- **Keep `_startup_events[crew_id]` until the next leader pops it**: Change the pop from the leader's `finally` to the new leader's setup block. This avoids the window entirely but requires a different pop site, which is a larger structural change and harder to audit.
- **Generation counter in a separate dict**: Chosen. Simple, explicit, easy to test.

### D2: Fix `_finish_crew_setup` cookie-mint failure — add `_cleanup_crew` and registry cleanup

**In `_finish_crew_setup`** (line ~1788), change:
```python
cookie = _mint_cookie(podman, container, crew_url)
if not cookie:
    return {"error": f"Failed to mint session cookie for crew {crew_id}"}
```
to:
```python
cookie = _mint_cookie(podman, container, crew_url)
if not cookie:
    _cleanup_crew(podman, container, volume, home_volume)
    return {"error": f"Failed to mint session cookie for crew {crew_id}"}
```

**In `launch()` in `server.py`** (line ~2078), check for error-dict return:
```python
result = _finish_crew_setup(...)
if "error" in result:
    # _finish_crew_setup may have already called _cleanup_crew internally,
    # but the registry placeholder entry must also be removed here.
    with _registry_lock:
        reg = _load_registry()
        reg["crews"].pop(crew_id, None)
        _save_registry(reg)
    if dashboard_port is not None:
        _caddy_portal.release_port(dashboard_port)
    return result
```

Note: the existing `launch()` code does not check for `"error"` in the result of `_finish_crew_setup`. Currently when `_finish_crew_setup` returns an error dict, it is passed straight to the caller without registry cleanup. This is the root cause of the orphaned-state problem on error-dict paths; the `except` block below handles the exception case but not the error-dict case.

## Risks / Trade-offs

- **CR-1 waiter raises instead of retrying**: The third waiter gets a RuntimeError rather than transparently getting the new leader's result. This is intentional — the caller (usually `_crew_api_with_recovery`) will surface the error to the user, who can retry. Transparent retry would require passing the whole `(crew, crew_id)` context into the waiter loop, which is architecturally messy.
- **Registry cleanup in `launch()` is now two-phase**: `_cleanup_crew` handles Podman objects; `launch()`'s error path handles the registry. This was already the pattern for the `except` block. The error-dict path now mirrors it.

## Migration Plan

No migration needed. All changes are within the existing request-handling path. No schema changes, no config changes, no new dependencies.

Rollback: revert the two modified files.

## Implementation Notes

### `transport/lifecycle.py` changes

**Module level** (after line 244, alongside `_startup_events`):
```python
# TRN-157: generation counter — incremented when a new leader is elected,
# read by waiters to detect a new restart cycle starting before they read outcomes.
_startup_generation: dict[str, int] = {}
```

**`_ensure_crew_running` — waiter election block** (line ~589–608): extend as shown in D1.

**`_ensure_crew_running` — waiter outcome read** (line ~621–638): add generation check as shown in D1.

**`_ensure_crew_running` — leader finally block** (line ~759–762): no change needed; generation counter persists across cycles.

**`_finish_crew_setup` — cookie mint failure** (line ~1788): add `_cleanup_crew` call as shown in D2.

### `transport/server.py` changes

**`launch()` — after `_finish_crew_setup` call** (line ~2078): add error-dict detection and registry cleanup as shown in D2.

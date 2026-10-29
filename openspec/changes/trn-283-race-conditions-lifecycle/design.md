# Design

## Context

All three races are in `transport/lifecycle.py` and `transport/launcher.py`. The
transport is an async Starlette/uvicorn app; concurrent requests share a single
process and a single `Registry` instance protected by a threading lock. The existing
locking discipline is correct in intent but has three gaps.

## Goals / Non-Goals

**Goals:**
- Eliminate the three races with minimal surgical changes
- Add regression tests for each fix
- No behaviour change for the common (non-concurrent) case

**Non-Goals:**
- Refactoring the broader locking model
- Changing the registry persistence format
- Addressing test coverage gaps (those belong to TRN-284)

## Decisions

### D1: H-1 — Move cookie write inside the lock

**Location:** `transport/lifecycle.py`, `_refresh_cookie()`.

The current code pattern is:
```python
with registry:
    registry.save_crew(crew_id, entry)   # persists new cookie
# lock released here
crew["cookie"] = new_cookie              # ← race window
```

**Fix:** Move the dict mutation inside the `with registry:` block, before or after
the save — either order is correct since both happen under the lock:
```python
with registry:
    entry["cookie"] = new_cookie
    registry.save_crew(crew_id, entry)
crew["cookie"] = new_cookie  # also update the local reference (safe duplicate)
```

Actually simplest: just move `crew["cookie"] = new_cookie` to be the last line
inside the `with` block. The dict is the same object as `entry` so persistence
and the local reference are both updated atomically.

### D2: H-2 — Timestamp guard in reconcile write-back

**Location:** `transport/lifecycle.py`, `_reconcile_registry()`.

The snapshot captures `{cid: entry["created_at"]}` for all entries in `to_remove`.
The write-back re-checks each cid:

```python
with registry:
    for cid in to_remove:
        live_entry = registry._reg["crews"].get(cid)
        if live_entry is None:
            continue  # already gone
        if live_entry.get("created_at") != snapshot_created_at[cid]:
            continue  # re-registered since snapshot — skip
        del registry._reg["crews"][cid]
    registry.save()
```

The `created_at` field is set by `launch()` at registration time and never mutated,
making it a stable identity marker for a specific crew instance.

### D3: H-3 — Single-lock election in ensure_running

**Location:** `transport/launcher.py`, `ensure_running()` / `_ensure_running_inner()`.

The current pattern reads `_startup_events` outside the lock then enters a locked
election. The fix consolidates both under one lock:

```python
with self._lock:
    if crew_id in self._startup_events:
        event = self._startup_events[crew_id]
        # become a waiter — fall through
    else:
        event = threading.Event()
        self._startup_events[crew_id] = event
        # become leader — start container below
```

The early lock-free `_early_in_progress` check is removed; the lock is cheap enough
that acquiring it unconditionally is the correct approach.

## Risks / Trade-offs

- **D1** is a one-line move, zero risk.
- **D2** adds a dict lookup under the write-back lock — negligible cost; the `to_remove`
  set is typically small.
- **D3** removes the fast-path lock-free check, adding one lock acquisition per
  `ensure_running` call on already-running crews. The lock is uncontended in that
  case and the overhead is microseconds.

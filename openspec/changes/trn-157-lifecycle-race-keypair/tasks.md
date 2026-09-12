# Tasks: TRN-157 — Generation-Counter Race + Admiral Keypair TOCTOU

## Task 1: Add `_startup_generation` module-level dict

**File**: `transport/lifecycle.py`
**Location**: After the `_crew_restart_outcomes` declaration (line ~244)

Add:
```python
# TRN-157: generation counter — tracks restart cycle identity per crew.
# Incremented when a new leader is elected; waiters capture the generation before
# event.wait() and verify it is unchanged after waking, so a third concurrent caller
# starting a new cycle cannot corrupt a prior waiter's outcome read.
# Guarded by _startup_events_lock (same lifecycle as _startup_events).
_startup_generation: dict[str, int] = {}
```

---

## Task 2: Capture and verify generation in `_ensure_crew_running` — waiter path

**File**: `transport/lifecycle.py`
**Function**: `_ensure_crew_running` (line ~589)

### 2a. Capture generation at election time

In the existing `with _startup_events_lock:` block that elects leader/waiter (lines 589–608), extend to:

```python
with _startup_events_lock:
    if crew_id in _startup_events:
        event = _startup_events[crew_id]
        is_leader = False
        # TRN-157: capture generation before releasing lock
        _waiter_gen = _startup_generation.get(crew_id, 0)
    else:
        event = threading.Event()
        _startup_events[crew_id] = event
        is_leader = True
        _crew_restart_outcomes.pop(crew_id, None)
        # TRN-157: increment generation for this new restart cycle
        _startup_generation[crew_id] = _startup_generation.get(crew_id, 0) + 1
        _waiter_gen = _startup_generation[crew_id]  # leader also captures (unused but symmetric)
```

### 2b. Verify generation after `event.wait()` returns

The existing waiter block starting at line ~610:

```python
if not is_leader:
    logger.info("Crew %s restart already in progress — waiting", crew_id)
    event.wait(timeout=45)
    # TRN-157: check generation under lock before reading outcome
    with _startup_events_lock:
        outcome = _crew_restart_outcomes.get(crew_id)
        _current_gen = _startup_generation.get(crew_id, 0)
    if _current_gen != _waiter_gen:
        raise RuntimeError(
            f"Crew {crew_id} restart (concurrent) failed -- restart cycle changed "
            f"during wait (waited on gen {_waiter_gen}, current gen {_current_gen}); "
            f"a new restart cycle started before outcome was read"
        )
    # ... existing outcome-read logic (outcome is None check, success/exc check) ...
```

**Note**: The generation check runs before the `outcome is None` check. A generation mismatch is a distinct failure mode; the outcome check still runs after generation is verified stable.

---

## Task 3: Fix `_finish_crew_setup` — add `_cleanup_crew` before cookie-mint failure return

**File**: `transport/lifecycle.py`
**Function**: `_finish_crew_setup` (line ~1788)

Change:
```python
cookie = _mint_cookie(podman, container, crew_url)
if not cookie:
    return {"error": f"Failed to mint session cookie for crew {crew_id}"}
```

To:
```python
cookie = _mint_cookie(podman, container, crew_url)
if not cookie:
    _cleanup_crew(podman, container, volume, home_volume)  # TRN-157: remove admiral secret
    return {"error": f"Failed to mint session cookie for crew {crew_id}"}
```

This matches the pattern already used for the two gateway-timeout error returns at lines ~1719–1720 and ~1747–1748.

---

## Task 4: Fix `launch()` — handle `_finish_crew_setup` error-dict returns

**File**: `transport/server.py`
**Function**: `launch()` (line ~2078)

The current call:
```python
result = _finish_crew_setup(podman, crew_id, container, volume, home_volume, auth_b64, composition, composition_entry, admiral_secret=_admiral_secret_hex, dashboard=effective_dashboard)
```

Add error-dict handling immediately after:
```python
result = _finish_crew_setup(...)
# TRN-157: _finish_crew_setup error-dict paths have already called _cleanup_crew
# (removing the admiral secret and Podman resources). The registry placeholder
# entry written before the try block still exists and must be removed here.
if "error" in result:
    with _registry_lock:
        reg = _load_registry()
        reg["crews"].pop(crew_id, None)
        _save_registry(reg)
    if dashboard_port is not None:
        try:
            _caddy_portal.release_port(dashboard_port)
        except Exception:
            pass
    return result
```

This mirrors the existing `except Exception` block at line ~2100 which already handles the exception path and cleans the registry.

---

## Task 5: Write unit tests

**File**: `transport/tests/test_trn157_lifecycle_race_keypair.py` (new file)

### CR-1 tests

1. **`test_three_caller_generation_check_raises`**: Set up `_startup_events`, `_crew_restart_outcomes`, and `_startup_generation` to simulate leader A having fired the event and a new leader C having incremented the generation. Call the waiter-path code directly. Assert `RuntimeError` is raised with the generation mismatch message rather than a spurious "leader did not record an outcome" error.

2. **`test_two_caller_normal_case_unaffected`**: Leader succeeds; waiter captures gen=1, wakes, gen is still 1. Assert waiter reads `(True, None)` and returns normally.

3. **`test_leader_failure_propagated_to_waiter`**: Leader fails with a known exception; gen remains the same (no third caller). Assert waiter re-raises the stored exception.

### CR-2 tests

4. **`test_finish_crew_setup_cookie_failure_calls_cleanup`**: Mock `_mint_cookie` to return `None`. Assert `_cleanup_crew` is called and the return value is `{"error": ...}`.

5. **`test_launch_cleans_registry_on_finish_crew_setup_error_dict`**: Mock `_finish_crew_setup` to return `{"error": "test"}`. Assert the registry placeholder entry for the crew is removed and `_caddy_portal.release_port` is called if `dashboard_port` was allocated.

6. **`test_no_orphaned_admiral_secret_after_failed_launch`**: Integration-style test. Mock Podman to succeed on `secret_create` then fail on `_wait_gateway`. Assert `_cleanup_crew` is called (which calls `podman.secret_remove`).

# Tasks: TRN-156 — Lifecycle Memory Leak + One-Shot Cron Annual Replay

## Task 1: Add TTL eviction to `_task_timestamps` in `_pickup_single`

**File**: `transport/lifecycle.py`
**Function**: `_pickup_single` (line ~2484)

Inside the `with _task_timestamps_lock:` block, after the existing timestamp update and snapshot logic (after line ~2494 where `ts = dict(ts)` is taken), add eviction of completed entries older than `_TASK_TIMESTAMP_TTL_SECS`:

```python
# TRN-156: evict completed-task timestamp entries older than TTL
_ttl_secs = float(os.environ.get("GA_TASK_TIMESTAMP_TTL_SECS", "3600"))
_evict_before = now.timestamp() - _ttl_secs
_to_evict = [
    k for k, v in _task_timestamps.items()
    if v.get("completed_at") is not None
    and datetime.fromisoformat(v["completed_at"]).replace(
        tzinfo=timezone.utc if datetime.fromisoformat(v["completed_at"]).tzinfo is None else None
    or timezone.utc).timestamp() < _evict_before
]
for k in _to_evict:
    _task_timestamps.pop(k, None)
```

Simpler version (avoid fromisoformat overhead in the hot path):
```python
_ttl_secs = float(os.environ.get("GA_TASK_TIMESTAMP_TTL_SECS", "3600"))
_evict_cutoff = (now - timedelta(seconds=_ttl_secs)).isoformat()
_to_evict = [
    k for k, v in _task_timestamps.items()
    if v.get("completed_at") is not None and v["completed_at"] < _evict_cutoff
]
for k in _to_evict:
    _task_timestamps.pop(k, None)
```

Note: `timedelta` is not yet imported in `lifecycle.py`; add `from datetime import datetime, timedelta, timezone` or use `datetime.now(timezone.utc) - timedelta(...)`.

**Acceptance**: After `GA_TASK_TIMESTAMP_TTL_SECS=5` (5 seconds), dispatch a task, wait 6 seconds, call pickup — the entry for any task completed before the cutoff should be absent from `_task_timestamps` after the pickup call.

---

## Task 2: Add TTL eviction to `_task_timestamps` in `_pickup_list`

**File**: `transport/lifecycle.py`
**Function**: `_pickup_list` (line ~2590)

Same eviction block as Task 1, added inside the `with _task_timestamps_lock:` section after the `_ts_snapshot` dict comprehension (line ~2594). The eviction runs before `_ts_snapshot` is used to build `task_list`, but reads from `_task_timestamps` (not `_ts_snapshot`) — evict first, then snapshot.

---

## Task 3: Add TTL eviction to `_warm_markers` in `_prewarm_crew`

**File**: `transport/lifecycle.py`
**Function**: `_prewarm_crew` (line ~857)

Inside the `with _warm_markers_lock:` block after writing the new marker (line ~858), add eviction of stale entries:

```python
# TRN-156: evict warm markers older than twice the prewarm TTL (or 1h minimum)
_wm_ttl = max(GA_PREWARM_TTL_SECS * 2 if GA_PREWARM_TTL_SECS > 0 else 3600, 3600)
_wm_now = time.monotonic()
_expired_wm = [k for k, v in _warm_markers.items() if (_wm_now - v) > _wm_ttl]
for k in _expired_wm:
    _warm_markers.pop(k, None)
```

**Acceptance**: With `GA_PREWARM_TTL_SECS=1` (so `_wm_ttl = max(2, 3600) = 3600`), entries older than 3600 s are removed. In tests, manually insert a stale entry with `time.monotonic() - 7200` and verify it is evicted on the next `_prewarm_crew` call.

---

## Task 4: Reorder one-shot job cleanup in schedule monitor — registry-first

**File**: `transport/monitors.py`
**Function**: `_schedule_monitor` (line ~273)

Replace the existing one-shot block:

```python
# EXISTING (fragile — DELETE before registry update):
if sched.get("one_shot"):
    job_id = sched.get("job_id")
    if job_id:
        try:
            _crew_api_with_recovery(crew, crew_id, "DELETE", f"/api/crons/{job_id}")
            logger.info("Schedule monitor: deleted one-shot cron %s from gateway after fire", job_id)
        except Exception as e:
            logger.warning("Schedule monitor: could not delete one-shot cron %s from gateway: %s", job_id, e)
```

With:

```python
# TRN-156: registry-first disablement — prevents annual replay if DELETE fails
if sched.get("one_shot"):
    job_id = sched.get("job_id")
    if job_id:
        # Step 1: mark disabled in registry (durable safety gate)
        try:
            with _registry_lock:
                _reg = _load_registry()
                for _s in _get_crew_schedules(_reg, crew_id):
                    if _s.get("job_id") == job_id:
                        _s["enabled"] = False
                        _s["next_fire_at"] = _NEVER_FIRE_AT
                        break
                _save_registry(_reg)
        except Exception as e:
            logger.warning(
                "Schedule monitor: could not disable one-shot cron %s in registry: %s",
                job_id, e,
            )
        # Step 2: best-effort DELETE from gateway
        try:
            _crew_api_with_recovery(crew, crew_id, "DELETE", f"/api/crons/{job_id}")
            logger.info(
                "Schedule monitor: deleted one-shot cron %s from gateway after fire",
                job_id,
            )
        except Exception as e:
            logger.warning(
                "Schedule monitor: could not delete one-shot cron %s from gateway: %s",
                job_id, e,
            )
```

Note: `_registry_lock`, `_load_registry`, `_get_crew_schedules`, `_save_registry`, and `_NEVER_FIRE_AT` are already imported in `monitors.py` (lines 47–62).

**Acceptance**: In a test where `_crew_api_with_recovery` raises on the DELETE call, verify that after the schedule monitor runs, the registry entry for the one-shot job has `enabled=False` and `next_fire_at=_NEVER_FIRE_AT`, and that the schedule monitor does NOT fire the job again in a subsequent cycle.

---

## Task 5: Write unit tests

**File**: `transport/tests/test_trn156_lifecycle_memory_cron.py` (new file)

Tests to write:

1. **`test_task_timestamps_eviction_in_pickup_single`**: Patch `_task_timestamps` with a mix of fresh completed, old completed, and in-progress entries. Call `_pickup_single`. Assert old completed entries are removed; fresh completed and in-progress are retained.

2. **`test_task_timestamps_eviction_in_pickup_list`**: Same but calling `_pickup_list`.

3. **`test_warm_markers_eviction`**: Inject stale entries into `_warm_markers` (monotonic timestamp far in the past). Call `_prewarm_crew` with a mock that returns immediately. Assert stale entries are evicted.

4. **`test_one_shot_registry_disabled_before_delete`**: Mock `_crew_api_with_recovery` to raise on DELETE. Run the one-shot block. Assert registry entry has `enabled=False` and `next_fire_at=_NEVER_FIRE_AT`. Assert schedule monitor does not fire in next cycle.

5. **`test_one_shot_delete_success_still_disables_registry`**: Mock DELETE to succeed. Assert registry entry still has `enabled=False` (the disable step runs unconditionally before DELETE).

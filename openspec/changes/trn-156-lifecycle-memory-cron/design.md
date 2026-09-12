# Design: TRN-156 — Lifecycle Memory Leak + One-Shot Cron Annual Replay

## Context

See `proposal.md — Why` for motivation.

Three module-level data structures in `transport/lifecycle.py` and `transport/monitors.py` are relevant:

- `_task_timestamps: dict[str, dict]` (line 2297) — keyed by `task_id`. Written by dispatch, read/updated by pickup. Never pruned. At 1 task/minute, 365 days = 525,600 entries; each ~200 bytes → ~100 MB/year.
- `_warm_markers: dict[str, float]` (line 256) — keyed by `crew_id`. Updated on every successful prewarm. Bounded by number of crews in practice, but never evicted.
- One-shot cron expression format (server.py line 2922): `f"{fire_at.minute} {fire_at.hour} {fire_at.day} {fire_at.month} *"` — the wildcard `*` in the year position means the cron expression matches the same minute/hour/day/month in every subsequent year. The schedule monitor fires and then tries to DELETE from the gateway; if the DELETE fails, the cron fires again next year.

Lock hierarchy (unchanged by this change):
- `_task_timestamps_lock` guards `_task_timestamps`
- `_warm_markers_lock` guards `_warm_markers`
- `_registry_lock` guards the persistent registry

## Goals / Non-Goals

**Goals:**
- Bound `_task_timestamps` memory growth to at most `_TASK_TIMESTAMP_TTL_SECS` (1 hour default) of completed entries
- Bound `_warm_markers` memory growth to at most `_WARM_MARKER_TTL_SECS` seconds of entries
- Make one-shot job re-fire survivable through a DELETE failure without any gateway-side fix

**Non-Goals:**
- Persisting task timestamps across transport restarts (D1: already accepted as lost-on-restart)
- Changing the one-shot cron expression format itself (fixing the expression to use a specific year is an alternative; see Decisions)
- Centralised background eviction thread (adds complexity; piggybacking on existing call paths is sufficient)

## Decisions

### D1: Piggyback eviction on existing pickup calls rather than a background thread

Alternatives considered:
- **Background eviction thread** (e.g. every 60 s): adds a thread, a new lock interaction, and a startup/teardown path. The existing pickup loop already holds `_task_timestamps_lock` and iterates the map — eviction here is zero additional lock overhead.
- **Size cap instead of TTL**: evict the oldest N entries when the map exceeds M entries. Harder to reason about; a burst of fast-completing tasks could evict entries that the caller still expects to find. TTL is more predictable.

**Decision**: Piggyback on pickup. In `_pickup_single` and `_pickup_list`, after updating the current task's timestamps under `_task_timestamps_lock`, scan the map for entries where `completed_at` is non-null and `datetime.fromisoformat(completed_at) < (now - TTL)`. Build a list of keys to delete, then delete them. The scan is O(N) but N is bounded to at most `TTL / avg_task_duration` entries under steady state.

### D2: Warm marker eviction piggybacked on `_prewarm_crew`

The `_warm_markers` dict is bounded in practice by the number of distinct crew_ids ever prewarmed. Eviction is a one-liner inside the existing `_warm_markers_lock` section. No separate thread needed.

### D3: Fix one-shot replay by registry-first disablement

Alternatives considered:
- **Use a fixed year in the cron expression** (e.g. `30 14 12 9 2026`): Most cron implementations do not support a year field; the KiroCrew gateway cron parser likely rejects it. Risky without confirmed gateway support.
- **Delete from gateway BEFORE advancing `next_fire_at`**: If the DELETE fails, the monitor might re-fire before the registry is updated — same problem.
- **Registry-first disable, then DELETE**: The registry `enabled: false` + `next_fire_at = _NEVER_FIRE_AT` is written under `_registry_lock` before the DELETE. The schedule monitor checks `next_fire_at > now` and `enabled` before firing (monitors.py line ~163). If the DELETE then fails, the monitor will never fire the job again because neither condition passes.

**Decision**: Registry-first. Order of operations in `_schedule_monitor` for one-shot jobs:

```python
# After successful fire (or even failed fire — the job has been attempted):
if sched.get("one_shot"):
    # 1. Disable in registry first — durable safety gate
    with _registry_lock:
        reg = _load_registry()
        for s in _get_crew_schedules(reg, crew_id):
            if s.get("job_id") == sched.get("job_id"):
                s["enabled"] = False
                s["next_fire_at"] = _NEVER_FIRE_AT
                break
        _save_registry(reg)
    # 2. Best-effort DELETE from gateway
    try:
        _crew_api_with_recovery(crew, crew_id, "DELETE", f"/api/crons/{job_id}")
    except Exception as e:
        logger.warning("Schedule monitor: could not delete one-shot cron %s: %s", job_id, e)
```

The registry write runs **regardless of whether the task dispatch fired**. If the dispatch failed, the one-shot is still disabled to prevent future attempts (the user should re-create the delay job if they want a retry).

## Risks / Trade-offs

- **Eviction scan O(N)**: Under heavy dispatch (1000+ concurrent tasks), pickup calls do an O(N) scan. At a 1-hour TTL the map is bounded to ~3600 entries/hour of dispatch rate. A pickup call scanning 3600 entries while holding the lock adds ~microseconds. Acceptable.
- **One-shot disable on dispatch failure**: If the task dispatch fails (e.g. crew unresponsive), the one-shot is still disabled. The operator must re-create the delay job. This is acceptable — a failed dispatch means the job was not completed; the correct action is to diagnose and re-schedule explicitly.

## Migration Plan

No migration needed. The changes are purely additive in-process behavior:
- Eviction reduces memory; existing entries continue to work until they age out.
- One-shot registry-first disable is a reordering of existing operations.
- No registry schema changes, no new config fields required (TTL constants have env-var overrides for operators who want to tune).

Rollback: revert the two modified files. No persistent state is affected.

## Implementation Notes

### `transport/lifecycle.py` changes

**`_pickup_single` (line ~2484)**:
```python
# Inside the `with _task_timestamps_lock:` block, after updating ts:
# Evict completed entries older than TTL
_now_epoch = now.timestamp()
_ttl = float(os.environ.get("GA_TASK_TIMESTAMP_TTL_SECS", "3600"))
_expired = [
    k for k, v in _task_timestamps.items()
    if v.get("completed_at") is not None
    and (_now_epoch - datetime.fromisoformat(v["completed_at"]).timestamp()) > _ttl
]
for k in _expired:
    _task_timestamps.pop(k, None)
```

**`_pickup_list` (line ~2590)**: Same eviction block inside the `with _task_timestamps_lock:` section, after building `_ts_snapshot`.

**`_prewarm_crew` (line ~857)**:
```python
# Inside `with _warm_markers_lock:`, after writing the new marker:
_wm_ttl = max(GA_PREWARM_TTL_SECS * 2, 3600)
_wm_now = time.monotonic()
_expired_wm = [k for k, v in _warm_markers.items() if (_wm_now - v) > _wm_ttl]
for k in _expired_wm:
    _warm_markers.pop(k, None)
```

### `transport/monitors.py` changes

**`_schedule_monitor` one-shot block (line ~273)**:

Replace the existing:
```python
if sched.get("one_shot"):
    job_id = sched.get("job_id")
    if job_id:
        try:
            _crew_api_with_recovery(crew, crew_id, "DELETE", f"/api/crons/{job_id}")
            ...
        except Exception as e:
            logger.warning(...)
```

With the registry-first pattern described in D3 above.

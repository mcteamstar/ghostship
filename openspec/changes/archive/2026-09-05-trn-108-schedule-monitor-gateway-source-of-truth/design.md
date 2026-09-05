## Context

See proposal.md for motivation. The current `_schedule_monitor` loop in `transport/lifecycle.py` (line ~1413) reads `sched.get("enabled", True)` from the transport registry to gate each job before firing:

```python
for sched in schedules:
    if not sched.get("enabled", True):   # <-- reads registry, stale after pause
        continue
    next_fire = sched.get("next_fire_at", _NEVER_FIRE_AT)
    if next_fire > now:
        continue

    # Job is due — wake the crew and fire
    crew = _ensure_crew_running(info, crew_id)
    ...
    _crew_api_with_recovery(crew, crew_id, "POST", "/api/spawn", json=tick_body)
```

The bug: if Raven paused the captain cron via `kirocrew cron pause` inside the container, the gateway shows `enabled: false`, but the registry still shows `enabled: true` (TRN-82 only syncs on restart). The monitor wakes the crew and fires the job.

The idle monitor already has the correct pattern: after waking the crew it fetches `/api/crons` and calls `_cron_has_enabled_job`. That pattern is the model for this fix.

Gateway cron payload shape (from `/api/crons`):
```json
{
  "jobs": [
    { "id": "<job_id>", "name": "captain", "enabled": false, "is_running": false, "last_run_ts": 1234567890, ... }
  ]
}
```

The job is matched from the gateway payload by `job["id"] == sched["job_id"]` — the same key used in `_reseed_cron_jobs`.

## Goals / Non-Goals

**Goals:**
- Schedule monitor reads `enabled` from the live gateway after waking the crew, not from the registry.
- When gateway says disabled, write `enabled: false` back to the registry so the registry stays in sync.
- Preserve the existing fallback: if the crew cannot be woken, advance `next_fire_at` and continue (unchanged). The fallback also falls back to registry `enabled` to handle the "was already stopped, gateway unreachable" case cleanly.

**Non-Goals:**
- Changing how `_reseed_cron_jobs` works (already correct after TRN-82).
- Changing the idle monitor (already correct).
- Real-time sync from gateway to registry outside of the write-back on disable.

## Decisions

### Decision: Fetch /api/crons after waking the crew, match by job_id

After `_ensure_crew_running` succeeds and returns `crew`, fetch `/api/crons` via `_crew_api` (or directly via `_http.get` with `_crew_url`/`_crew_cookie` helpers). Find the job whose `id` matches `sched["job_id"]`. Use its `enabled` field.

**Why after wake, not before:** The crew may be stopped when the monitor runs. The gateway is only queryable when the container is running. Fetching before `_ensure_crew_running` would always fail for stopped crews.

**Why not use `_crew_api_with_recovery`:** The cron fetch is a read-only probe. A simple `_crew_api` call (which already uses `_http.request` + `raise_for_status()`) is sufficient and matches what `_reseed_cron_jobs` does. If it raises, we fall through to the existing error handler.

**Alternative considered — look up job_id in the registry's `sched["enabled"]`:** Already done, that's the bug. Discarded.

**Alternative considered — only fetch /api/crons once per crew per cycle:** A single `/api/crons` GET per crew per cycle would be efficient if multiple schedules exist for the same crew, but crews typically have one schedule (captain). Per-schedule fetches are simpler and avoid caching across multiple jobs. Premature optimisation; can be batched later if needed.

### Decision: Registry write-back when gateway says disabled

When the gateway fetch succeeds and reports `enabled: false`, write `enabled: false` to the matching registry entry under `_registry_lock`. This is a best-effort sync identical to the pattern in `_reseed_cron_jobs` and `_captain_checkin_job`.

This means the next cycle will skip the job at the cheap registry check before even waking the crew — improving performance in the common steady-state (paused job).

### Decision: Fallback to registry when gateway is unreachable after wake

If `_ensure_crew_running` raises (crew can't start), or the `/api/crons` call itself raises, fall back to `sched.get("enabled", True)`. The existing error path (advance `next_fire_at` + log warning) already handles the wake failure. We only need to add: skip if `sched.get("enabled", True)` is `False` in that path. This means a registry-disabled job is still honoured when the gateway is dead, which is safe.

## Precise code change

**Before** (lines ~1427–1432):

```python
for sched in schedules:
    if not sched.get("enabled", True):
        continue
    next_fire = sched.get("next_fire_at", _NEVER_FIRE_AT)
    if next_fire > now:
        continue

    # Job is due — wake the crew and fire
    try:
        crew = _ensure_crew_running(info, crew_id)
    except Exception as e:
        logger.warning(...)
        _advance_next_fire_at(sched)
        # ... persist next_fire_at ...
        continue

    # Fire the tick
    ...
```

**After:**

```python
for sched in schedules:
    # Cheap registry-enabled check first (fast path for already-synced disabled jobs).
    if not sched.get("enabled", True):
        continue
    next_fire = sched.get("next_fire_at", _NEVER_FIRE_AT)
    if next_fire > now:
        continue

    # Job is due — wake the crew and check gateway enabled state.
    try:
        crew = _ensure_crew_running(info, crew_id)
    except Exception as e:
        logger.warning(
            "Schedule monitor: crew %s won't start for job %s: %s",
            crew_id, sched.get("job_id"), e,
        )
        _advance_next_fire_at(sched)
        # ... persist next_fire_at (unchanged) ...
        continue

    # TRN-108: check gateway enabled state — gateway is source of truth.
    job_id = sched.get("job_id")
    try:
        cron_payload = _crew_api(crew, "GET", "/api/crons")
        gateway_jobs = cron_payload.get("jobs", []) if isinstance(cron_payload, dict) else []
        gateway_job = next(
            (j for j in gateway_jobs if isinstance(j, dict) and j.get("id") == job_id),
            None,
        )
        if gateway_job is not None and not gateway_job.get("enabled", True):
            # Gateway says disabled — write back to registry and skip.
            logger.info(
                "Schedule monitor: job %s on crew %s is disabled in gateway — skipping and syncing registry",
                job_id, crew_id,
            )
            with _registry_lock:
                reg = _load_registry()
                crew_scheds = _get_crew_schedules(reg, crew_id)
                for s in crew_scheds:
                    if s.get("job_id") == job_id:
                        s["enabled"] = False
                        break
                _save_registry(reg)
            continue
    except Exception as e:
        logger.warning(
            "Schedule monitor: could not fetch gateway cron state for job %s on crew %s: %s — proceeding",
            job_id, crew_id, e,
        )
        # Fail-open: proceed to fire if gateway unreachable after wake.

    # Fire the tick (unchanged from here)
    ...
```

The only structural change is the new gateway-fetch block inserted between `_ensure_crew_running` and the fire. All downstream logic (advance `next_fire_at`, `last_checkin_at`, one-shot delete) is unchanged.

## Risks / Trade-offs

[Risk: extra HTTP call per due job per cycle] → Mitigation: the gateway is already running (we just woke it); the call is a lightweight GET with a 5s timeout (same as the idle monitor). In the common case (captain check-in, one job per crew), one extra GET per 30s cycle is negligible.

[Risk: `/api/crons` returns unexpected shape] → Mitigation: same defensive `isinstance` checks as the idle monitor (`_cron_has_enabled_job`). A malformed payload leaves `gateway_job` as `None`, which falls through to fire (fail-open).

[Risk: write-back races with `_reseed_cron_jobs` on concurrent restart] → Mitigation: both paths hold `_registry_lock` and reload `_load_registry()` before writing, so the last writer wins deterministically. The reconcile pass in `_reseed_cron_jobs` would then overwrite the write-back on the next restart anyway, keeping the gateway authoritative end-to-end.

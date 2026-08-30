## Context

`_reseed_cron_jobs` runs after every container restart (called from `_ensure_crew_running`). Its job is to re-register scheduled jobs into a fresh gateway — necessary because the gateway's in-memory cron state is lost when the container stops.

The current implementation iterates the transport registry and registers any enabled job not already present in the gateway. This treats the registry as the source of truth. But any mutation made from inside the container (`kirocrew cron pause`, `cron resume`, `cron delete`) is visible in the gateway but not reflected in the registry. On the next restart, the registry's stale enabled state overwrites the gateway.

Root cause confirmed by inspection (TRN-75 debug session, 2026-08-30):
- Raven paused the captain cron via `kirocrew cron pause` → gateway: `"enabled": false`
- Transport registry: `"enabled": true` (never updated)
- On restart: `_reseed_cron_jobs` re-registered the captain cron as active
- Result: crew never idle-stopped

## Goals / Non-Goals

**Goals:** Reconcile registry from gateway on every restart. Gateway wins on any conflict. Jobs paused, resumed, or deleted inside the container are correctly reflected in the registry after the next restart.

**Non-Goals:** Real-time sync (the gateway is only queryable when the container is running). Handling jobs created inside the container that have no registry entry (these are not transport-managed and are out of scope).

## Decisions

### Reconcile before reseed

**Decision:** Split `_reseed_cron_jobs` into two passes:

1. **Reconcile pass** — read `/api/crons` from the gateway; for each job the gateway reports, find the matching registry entry by `job_id` and update its `enabled` field (and `interval_secs`/`cron_expr` if they differ). Remove registry entries whose `job_id` is absent from the gateway.

2. **Reseed pass** — for each registry entry that has no matching `job_id` in the gateway, register it (existing behaviour, unchanged).

The reconcile pass runs first so the reseed pass only bootstraps genuinely missing jobs.

### Matching by job_id

Jobs are matched between gateway and registry by `job_id`. The gateway returns an `id` field; the registry stores `job_id`. This is already the matching key used in the existing reseed loop.

### Handling gateway errors

If `/api/crons` returns an error, skip both passes for this crew — the existing fail-open behaviour is preserved. Do not reconcile with stale data.

### Registry write on reconcile

Registry updates from the reconcile pass are written atomically via `_save_registry` under `_registry_lock`, matching the existing pattern.

## Impact

- `transport/server.py` — `_reseed_cron_jobs`: add reconcile pass before existing reseed loop; update registry enabled/interval fields from gateway; remove orphaned registry entries
- `tests/unit/` — 3 new test cases covering the three reconcile scenarios

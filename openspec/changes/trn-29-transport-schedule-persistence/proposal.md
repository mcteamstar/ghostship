# Proposal: trn-29-transport-schedule-persistence

## Why

Scheduled jobs (captain check-ins, recurring tasks) are stored inside the crew container via the KiroCrew gateway cron API. If a crew goes idle and the container stops, the schedule is effectively paused — the gateway cron ticker is frozen, and nothing wakes the container back up to fire the next tick. The result: a captain loop set to every 10 minutes silently stops firing if the crew idles out between ticks (default idle timeout is 5 minutes).

The fix is a **dual-log model**: the transport registry mirrors the gateway's schedule log. Both are kept in sync. The gateway remains the executor (it fires ticks, tracks last_run, etc.); the transport log is the durable backing store that lets the transport:

1. **Wake idle crews before a scheduled tick fires** — transport knows a check-in is due, ensures the container is running, and the tick fires into a live gateway
2. **Re-seed the gateway on restart** — when a stopped crew comes back up, the transport re-registers its schedule into the gateway from the registry, so no jobs are lost
3. **Expose schedule state via MCP even when the crew is stopped** — list/cancel read from the transport registry, not the gateway (which may be unavailable)

The transport log and gateway log are treated as two views of the same truth. Writes go to both; on divergence (e.g. after a restart), the transport log wins.

## What Changes

- Transport stores scheduled job metadata in `crews.json` alongside each crew: `job_id`, `name`, `interval_secs`, `next_fire_at`, `agent`, `message`
- A transport-level scheduler loop (`_schedule_monitor`) checks for due jobs every ~30s, calls `_ensure_crew_running` if the crew is stopped, then fires the dispatch via the crew gateway REST API
- On crew restart/reconciliation (`_reconcile_registry`), transport re-registers tracked jobs into the gateway cron API so the gateway and transport stay in sync
- Captain orders write to both the gateway cron API (for in-container execution) and the transport registry (for wake-up persistence)
- The `schedule` tool's `list` and `cancel` actions (TRN-23) read from the transport registry as the authoritative source rather than proxying the gateway — making them available even when the crew is stopped
- **`dispatch delay=N` is removed** — `delay` moves to the `schedule` tool as a first-class parameter alongside `interval` and `cron`. `dispatch` becomes purely immediate (always returns `task_id`). `schedule delay=N` creates a one-shot job that fires once after N seconds and returns a `job_id`. This cleans up the broken abstraction where `dispatch delay` returned a `job_id` instead of a `task_id`.

## Capabilities

### Modified Capabilities

- `autonomous-orchestration` — Captain check-ins and scheduled tasks fire reliably regardless of crew idle state. Schedule list/cancel work on stopped crews.
- `idle-and-recovery` — `_reconcile_registry` gains schedule re-registration as part of startup recovery.
- `task-orchestration` — Transport is the authoritative schedule store; gateway cron is a secondary executor, not the source of truth.

## Impact

- `transport/server.py` — `_schedule_monitor` loop, registry schedule storage, captain order writes, `_reconcile_registry` schedule sync, `schedule` tool list/cancel read path
- `crews.json` schema — new `schedules` array per crew entry
- Relates to TRN-23 (schedule cancel/list) — TRN-23 may land first; TRN-29 extends the list/cancel read path to use the transport registry

## Dependencies

- TRN-23 (schedule management) — should be designed with TRN-29 in mind; the list/cancel surface is shared

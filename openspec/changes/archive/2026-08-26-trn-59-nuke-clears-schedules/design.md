# Design: trn-59-nuke-clears-schedules

## Context

See `proposal.md - Why` for motivation.

The relevant code is in `transport/server.py`. The `nuke()` function has two paths:

1. **Dry-run** (`confirm=False`): reads the registry entry, queries the gateway for active tasks, returns a summary without taking any action.
2. **Confirmed** (`confirm=True`): calls `_cleanup_crew()` to stop the container and remove volumes, then pops the crew from the registry under `_registry_lock`.

Schedule data lives in `crews.json` as a `schedules` list per crew entry (introduced by TRN-29). Each entry has `job_id`, `name`, `interval_secs`, `cron_expr`, `next_fire_at`, `agent`, `message`, and `enabled`. The `_schedule_monitor` background thread reads this list on a 30-second poll cycle and fires any due jobs.

The gap: the dry-run does not read `schedules` at all, and the confirmed path pops the whole crew entry without first cancelling jobs at the gateway. The registry deletion implicitly removes schedule data, so `_schedule_monitor` won't fire orphan jobs — but the operator has no visibility into what was lost, and running gateway jobs aren't explicitly cancelled (they die with the container, but no clean acknowledgment is given).

## Goals / Non-Goals

**Goals:**
- Dry-run surfaces `scheduled_jobs` count and `scheduled_job_names` list so operators see impact before confirming.
- Confirmed nuke issues `DELETE /api/crons/<job_id>` for each registry schedule entry before tearing down the container.
- All schedule data removed from registry as part of the existing atomic registry write (crew pop already handles this — no separate step needed).
- Unreachable gateway is tolerated: cancellation errors are logged, teardown proceeds.

**Non-Goals:**
- Preserving or migrating schedules to another crew — nuke is destructive by design.
- Cancelling gateway-only jobs that are not tracked in the transport registry (backward-compat stale state). Those die with the container anyway; this change targets the authoritative transport registry.
- Changing the `schedule(action="cancel")` path — that already handles individual job cancellation correctly.

## Decisions

**Decision: Best-effort cancellation, not atomic.**
Attempting to cancel gateway jobs before teardown could fail (stopped container, network issue). Making teardown conditional on successful cancellation would be a regression — nuke must reliably destroy the crew. Best-effort (try DELETE, log WARNING on failure, continue) is the right trade-off: it cleans up in the happy path without blocking the destructive path.

Alternative considered: skip gateway cancellation entirely (the container dies so jobs die too). Rejected because it leaves the gateway in a dirty state if the container survives partially (e.g. `_cleanup_crew` stops but doesn't remove the container before a failure). Explicit DELETE is cleaner and costs one HTTP call per schedule.

**Decision: `_get_crew_schedules` from registry for dry-run, not from gateway.**
The registry is the authoritative source (TRN-29 established this). Querying the gateway for the dry-run count would require starting the crew if stopped, and would be inconsistent with `schedule(action="list")` which reads the registry. Dry-run reads registry schedules only.

**Decision: Cancellation loop uses `_crew_api` directly (not `_crew_api_with_recovery`).**
`_crew_api_with_recovery` restarts the container on failure — we don't want to restart a container we're about to destroy. Use bare `_crew_api` wrapped in a try/except, consistent with the pattern in the dry-run's active-task query.

## Risks / Trade-offs

- [Race condition] A schedule tick fires between the cancellation loop and `_cleanup_crew`. → The `_schedule_monitor` will fail to fire any tick whose crew no longer exists in the registry after the pop. Acceptable: the pop is the definitive state change; the tick might dispatch one extra agent turn that fails immediately when it can't reach the crew. No data corruption.
- [Partial cancellation] Gateway `DELETE` fails for some jobs before container teardown. → Those jobs are already cleaned from the registry (crew pop), so `_schedule_monitor` won't revive them. Gateway crons also die with the container. The only residue is a gateway-side job entry in a container that no longer exists — not a practical concern.

## Migration Plan

This is an additive change to a single function. No data migration is needed: existing `crews.json` files are unchanged in schema; the new dry-run fields are additive (existing callers can ignore them). No restart beyond the normal transport update cycle is required.

## Open Questions

_(none)_

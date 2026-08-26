# Proposal: trn-59-nuke-clears-schedules

## Why

When `nuke` tears down a crew, any scheduled jobs registered against that crew are silently abandoned: the transport registry entry is deleted (taking the `schedules` list with it), but the confirmation dry-run never surfaces how many schedules existed, and no explicit cancellation is issued to the gateway before the container is destroyed. Operators lose visibility into what recurring work was scheduled and get no chance to react before it disappears.

## What Changes

- The `nuke` dry-run (called without `confirm=True`) SHALL include the count and names of scheduled jobs in its response, alongside the existing `active_tasks` count, so the operator knows what will be lost before confirming.
- `nuke(confirm=True)` SHALL explicitly cancel all scheduled jobs from the transport registry (issuing `DELETE /api/crons/<job_id>` to the gateway for each) before tearing down the container and removing the registry entry.
- If the gateway is unreachable at nuke time (container already stopped or failing), the cancellation step is best-effort: the transport proceeds with container/volume removal and registry deletion regardless, logging any cancellation errors at `WARNING` level.
- The spec for `crew-lifecycle` gains a new requirement that codifies both behaviours: dry-run schedule reporting and confirmed-nuke schedule clearing.
- The spec for `task-orchestration` gains a supporting requirement that the transport schedule registry is cleared as part of a confirmed nuke, maintaining the invariant that the registry only holds schedules for existing crews.

## Capabilities

### New Capabilities

_(none — this change extends existing capabilities)_

### Modified Capabilities

- `crew-lifecycle`: `nuke` dry-run gains a `scheduled_jobs` count field; confirmed nuke gains an explicit schedule-clearing step before container teardown.
- `task-orchestration`: Transport schedule registry entries for a crew are cleared atomically with the crew registry entry on confirmed nuke.

## Impact

- `transport/server.py` — `nuke()` function: dry-run return value gains `scheduled_jobs` field; confirmed-nuke code path gains gateway cron DELETE loop before `_cleanup_crew`.
- `openspec/specs/crew-lifecycle/spec.md` — new requirement scenarios for nuke schedule reporting and clearing.
- `openspec/specs/task-orchestration/spec.md` — new requirement/scenario tying schedule registry consistency to the nuke operation.
- No API surface changes to callers; existing nuke return shape is extended (additive).

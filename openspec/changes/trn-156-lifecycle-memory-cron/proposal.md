## Why

`_task_timestamps` and `_warm_markers` are module-level dicts in `transport/lifecycle.py` that grow without bound for the lifetime of the transport process, leaking memory proportional to total task dispatch and prewarm volume. Separately, one-shot (delay) jobs use a wildcard-year cron expression (`MM HH DD MON *`) that silently replays the following year if the gateway DELETE after firing fails, causing spurious duplicate task executions.

## What Changes

- Add a bounded TTL eviction for `_task_timestamps`: after a task's `completed_at` is set, evict its entry once `completed_at` is more than `_TASK_TIMESTAMP_TTL_SECS` (default 3600 s / 1 hour) in the past. Eviction runs inside the existing `_task_timestamps_lock`-guarded section of `_pickup_single` and `_pickup_list` at the end of each call.
- Add a bounded TTL eviction for `_warm_markers`: entries older than `GA_PREWARM_TTL_SECS * 2` (or a hard cap of `_WARM_MARKER_TTL_SECS = 3600 s`) are purged inside the existing `_warm_markers_lock`-guarded section in `_prewarm_crew` on each prewarm call.
- Fix the one-shot cron replay bug: after successfully firing a one-shot job, mark the registry entry `enabled: False` and set `next_fire_at` to `_NEVER_FIRE_AT` **before** issuing the gateway DELETE. If the DELETE fails, the registry state already prevents the schedule monitor from firing it again. Remove the registry entry only after a confirmed successful DELETE.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `crew-lifecycle`: The crew lifecycle spec does not currently constrain in-process memory management of task-timestamp state. Adding a requirement that completed-task timestamp entries be evicted within a bounded TTL window is a spec-level behavioral addition.
- `task-orchestration`: The one-shot job deletion guarantee is a task-orchestration behavior requirement. The current spec is silent on what happens if the gateway DELETE fails; this change adds an idempotent-delete requirement so a failed DELETE never causes replay.

## Impact

- `transport/lifecycle.py`: `_task_timestamps` eviction logic in `_pickup_single` (line ~2484) and `_pickup_list` (line ~2590); `_warm_markers` eviction in `_prewarm_crew` (line ~2857); schedule monitor one-shot deletion order in `monitors.py` (~line 275).
- `transport/monitors.py`: reorder one-shot handling — mark registry disabled before gateway DELETE.
- No API surface changes. No registry schema changes (uses existing `enabled` and `next_fire_at` fields). No new dependencies.

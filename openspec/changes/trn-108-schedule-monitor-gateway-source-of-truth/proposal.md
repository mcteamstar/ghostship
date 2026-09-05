## Why

The schedule monitor in `transport/lifecycle.py` reads `sched["enabled"]` from the ghostship registry (`crews.json`) to decide whether to fire a scheduled job. Since TRN-82 made the gateway the source of truth for cron state, this has been inconsistent: when Raven pauses the captain cron via `kirocrew cron pause` inside the container, the gateway shows `enabled: false` but the registry still shows `enabled: true`, causing the schedule monitor to restart the container and fire the job anyway.

## What Changes

- The schedule monitor will read the `enabled` field from the gateway's `/api/crons` response (already fetched to check `last_run_ts` and `is_running`) instead of from the registry's `sched["enabled"]`.
- When the gateway reports `enabled: false` for a job, the monitor skips firing and writes `enabled: false` back to the registry to keep it in sync.
- When the crew is stopped and the gateway is unreachable (crew can't be woken), the monitor falls back to the registry's `enabled` field to determine whether to skip — preserving the existing fail-open behaviour for stopped crews.

## Capabilities

### New Capabilities

_(none — this is a fix to existing monitor logic, not a new capability)_

### Modified Capabilities

- `idle-and-recovery`: Add requirement that the schedule monitor reads gateway cron state as the authoritative enabled signal, not the registry; registry write-back on gateway-disabled jobs; fallback to registry when the gateway is unreachable.

## Impact

- `transport/lifecycle.py` — `_schedule_monitor`: replace `sched.get("enabled", True)` guard with a gateway fetch and `enabled` field check; write back to registry when gateway reports disabled; fallback path when `_ensure_crew_running` fails or crew was already stopped.
- `tests/unit/test_lifecycle.py` — new unit tests covering: (1) monitor skips and writes back when gateway says disabled, (2) monitor fires when gateway says enabled, (3) fallback to registry when gateway unreachable.

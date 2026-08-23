## Context

Currently the captain loop and all scheduled jobs live exclusively inside the
crew's KiroCrew gateway cron service. When a crew idles out (after
`GA_IDLE_TIMEOUT_SECS`, default 300s) the container stops and the cron ticker
freezes. A 300s captain interval only works reliably because we explicitly set
it to match the idle timeout — a fragile band-aid.

TRN-29 makes the transport the authoritative schedule store. The gateway
becomes a secondary executor — it fires ticks, but the transport owns the
schedule state and drives wake-up.

## Goals / Non-Goals

**Goals:**
- Transport registry mirrors all scheduled jobs per crew
- `_schedule_monitor` background loop wakes idle crews before ticks fire
- `_reconcile_registry` re-seeds gateway on crew restart
- `schedule list/cancel` reads from transport registry (works on stopped crews)
- `delay` moves from `dispatch` to `schedule`; `dispatch` becomes purely immediate

**Non-Goals:**
- Distributed or multi-transport schedule coordination
- Per-tick result tracking in the transport (gateway owns execution history)
- Changing the gateway cron API

## Decisions

### 1. crews.json schema extension

Each crew entry gains a `schedules` list:
```json
{
  "crews": {
    "my-crew": {
      "schedules": [
        {
          "job_id": "abc123",
          "name": "captain",
          "interval_secs": 300,
          "cron_expr": null,
          "next_fire_at": 1787460000.0,
          "agent": "raven",
          "message": "<standing order text>"
        }
      ]
    }
  }
}
```
`interval_secs` XOR `cron_expr` — one is set, the other null.
`next_fire_at` is a Unix timestamp. The monitor advances it after each fire.

### 2. _schedule_monitor loop

Runs in a daemon thread alongside `_idle_monitor`. Polls every 30s:
```
for each crew in registry:
    for each job where next_fire_at <= now:
        _ensure_crew_running(crew_id)
        POST /api/crons/{job_id}/fire  (or re-dispatch via spawn)
        advance next_fire_at by interval_secs
```

The monitor uses `_ensure_crew_running` — same recovery path as any other
crew interaction. If the crew can't start, skip and advance.

### 3. Captain order writes to both surfaces

`captain(action="order")` currently writes to the gateway cron API only.
After this change it also writes a schedule entry to the registry. On resume
(paused → ordered), the registry entry is updated, not duplicated.

### 4. schedule list/cancel reads from registry

Currently `schedule(action="list")` proxies `GET /api/crons` from the gateway.
After this change, it reads from `crews.json` registry — available even when
the crew is stopped. Cancel updates both the registry and the gateway (if the
crew is running).

### 5. delay migration: dispatch → schedule

`dispatch` loses the `delay` parameter. `schedule` gains `delay=N` as a
one-shot mode alongside `interval` and `cron`. The implementation uses the
same cron-expression-at-a-future-time approach as before, but now goes through
the transport registry so it survives idle.

### 6. _reconcile_registry re-seeding

After a crew restarts, `_reconcile_registry` calls a new
`_reseed_crew_schedules(crew_id, crew_info)` helper that reads the
`schedules` list from the registry and re-registers each job in the gateway.
Jobs that already exist in the gateway (same `job_id`) are skipped.

## Migration Plan

Existing installations: on first deploy, `crews.json` has no `schedules` keys.
The monitor skips crews with empty/missing schedules lists. Existing captain
loops continue via the gateway as before until the next `captain(action="order")`
call, which writes the schedule entry into the registry.

# Design: TRN-214

See proposal.md for root cause and dead ends investigated.

## Context

Current flow:
```
transport → POST /api/crons (agent=raven) → cron:{id} session → execution_context=None → 409
```

New flow:
```
transport → dispatch(raven, slot=member-raven) → dashboard:member-raven session
                                                  execution_context captured ✓
         → /continue on task_id (each subsequent fire) → inherits execution_context ✓
```

Key facts confirmed from source:
- `continuation.py:441`: `execution = original.execution_context` — continuations inherit
- `_spawn_scope_refusal`: cookie-auth callers bypass scope check entirely (transport uses cookie)
- `/continue` returns a new `task_id` each call — transport must update registry
- `conversation_gone` 404 is the signal to fall back to fresh dispatch

## Architecture

```
transport registry (per crew, captain entry):
  {
    "type": "captain",
    "enabled": true,
    "interval_secs": 3600,       # or cron_expr
    "next_fire_at": 1234567890,
    "current_task_id": "abc123", # live member-raven session handle
    "order_message": "..."       # written to captain mailbox separately
  }

_captain_timer_loop (new background task):
  - runs alongside idle-monitor loop
  - wakes when any crew has a captain entry due
  - calls _steer_captain_checkin(crew_id)
  - updates next_fire_at

_steer_captain_checkin(crew_id):
  - POST /api/spawn/{current_task_id}/continue
  - on success: update current_task_id in registry
  - on conversation_gone: call _dispatch_captain_checkin(crew_id)

_dispatch_captain_checkin(crew_id):
  - dispatch(raven, _CAPTAIN_CHECKIN_TASK, slot=member-raven)
  - store new task_id as current_task_id in registry
```

## Decisions

**D1: dispatch+steer, no cron.**

The only path to `execution_context` is originating from an attested session.
`POST /api/crons` from the transport creates an unowned, unattested cron.
There is no post-hoc API to inject `execution_context`. dispatch into member-raven
is the only operator-accessible path that captures it correctly.

Alternative: have Raven create the cron herself from her member session (so the
gateway captures `execution_context` at creation). Rejected: requires transport to
dispatch Raven first, wait for her to create the cron, get the job_id back via
mailbox — async, fragile, harder to cancel. Dispatch+steer achieves the same result
with simpler state.

**D2: steer via `/continue`, not a new dispatch each time.**

Preserves session context across check-ins (Raven can track ongoing work). Aligns
with the existing steer() tool semantics. A fresh dispatch each time would work for
member identity but lose cross-check-in memory.

**D3: transport owns the timer.**

The gateway cron timer is no longer used for captain. Transport's `_captain_timer_loop`
wakes at `next_fire_at`, same pattern as the existing idle-monitor. This is
"moving scheduling responsibility to transport" deliberately — the tradeoff is that
the transport must stay running for captain to fire, which was already true (the
transport owns crew lifecycle).

**D4: `current_task_id` tracked per crew in registry.**

Registry already tracks captain schedule state. Adding `current_task_id` is minimal
— one field. On container restart, `_reseed_crew_schedules` checks liveness and
re-dispatches if dead.

**D5: `_CAPTAIN_CHECKIN_TASK` unchanged in substance.**

The standing orders still live in `captain@localhost`. The only thing that changes
is Raven no longer runs in a `cron:` prefixed session — she runs in her member slot.
References to "persistent session" context in the prompt can be removed but the
core task description is the same.

**D6: `schedule()` tool is unaffected.**

User-facing cron jobs via `schedule()` don't spawn sub-agents, so they don't hit
the `execution_context` gate. No change needed there.

## Risks / Trade-offs

**[Risk] Timer loop not running** → If transport restarts between fires, the next
startup calls `_reseed_crew_schedules` which checks `next_fire_at` and fires
immediately if overdue. Mitigation: existing reconcile-on-restart pattern.

**[Risk] `current_task_id` stale after container restart** → The task record is
in the container's memory/disk. `_reseed_crew_schedules` calls `/api/spawn/{task_id}`
— `conversation_gone` 404 triggers fresh dispatch. Mitigation: explicit recovery path.

**[Risk] Raven session grows unboundedly** → A single member-raven session
accumulating check-ins over days/weeks could hit context limits. Mitigation:
`minimal_context: true` is already set. KiroCrew's own session rotation handles
transcript trimming. Fresh dispatch fallback on container restart also resets context.

**[Risk] Race between timer firing and previous check-in still running** →
`/continue` returns `conversation_busy` 409 if the session is mid-turn. Transport
should back off and retry rather than double-fire. Mitigation: check task liveness
before firing; if still running, skip this tick and reschedule.

## Migration

1. Deploy new transport (transport-only change, no crew image rebuild)
2. Existing captain entries in registry have `job_id` (old cron model) — transport
   detects absence of `current_task_id` and re-dispatches on next reconcile
3. Old cron jobs in running containers are orphaned (not deleted) — harmless, they
   fire into headless sessions which fail silently as before. Can be cleaned up
   by nuking the crew or manually via the dashboard.
4. No rollback risk: if the new timer loop fails, captain simply doesn't fire.
   Worse than before (broken) but not worse in kind.

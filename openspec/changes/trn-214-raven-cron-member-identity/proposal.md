# TRN-214: Raven cron session lacks member identity on 0.8.0

## Problem

The entire Captain workflow (sdd, indy, free-form orders) is broken on KiroCrew 0.8.0.
Raven dispatched via `POST /api/crons` gets `member_identity_unavailable` (HTTP 409) when
it attempts `POST /api/spawn` inside a check-in.

## Root cause (confirmed via source trace)

`job.execution_context` is `None` for crons created externally via `POST /api/crons`.
The 409 comes from `internal_memory_scope` → `member_request_scope` →
`_cron_execution_from_registry`, which reads `job.execution_context` — not
`job.session_key`. With no execution context, member scope is unverified → 409.

Two dead ends investigated and ruled out:

- **`X-Session-Key` header** (TRN-206 partial fix) — sets `$KIRO_SESSION_ID` in the
  cron session but it's not an attested member key; gateway still rejects it.
- **`kirocrew cron adopt`** — sets `job.session_key` to `dashboard:member-raven`, but
  `session_key` only controls result delivery (which chat tab). `build_cron_session_context`
  always returns `cron:{job.id}` as the firing session; `execution_context` is never touched.

`execution_context` is only captured correctly when the spawn originates from within an
attested member session. There is no operator CLI or API surface to inject it post-hoc.

## Fix — dispatch + steer, no cron

Replace the Captain cron with a transport-driven dispatch+steer loop:

1. **First fire**: transport calls `dispatch(agent="raven", slot="member-raven")` → Raven
   runs in `dashboard:member-raven` — an attested member session with `execution_context`
   captured correctly. Transport stores `current_task_id` in the registry.

2. **Subsequent fires**: transport calls `/api/spawn/{task_id}/continue` (steer on
   completed task) → continuation inherits `execution_context` from the original dispatch
   (confirmed: `continuation.py:441` `execution = original.execution_context`). Same
   session accumulates context across check-ins. Transport updates `current_task_id`.

3. **Recovery**: if `current_task_id` is gone (`conversation_gone` 404), fall back to
   fresh `dispatch()` and update `current_task_id`.

4. **Stop**: set `enabled: false` in registry — no gateway cron to disable.

5. **Reseed on container restart**: if `enabled: true` and task is gone, re-dispatch.
   No `POST /api/crons` call at all for captain entries.

## What changes

**`transport/server.py` — `_captain_do_order`**: remove `POST /api/crons`. Write registry
entry `{ type: "captain", enabled, interval_secs, cron_expr, next_fire_at, current_task_id,
order_message }`. Fire immediately via `_dispatch_captain_checkin()`.

**`transport/server.py` — `_captain_stop`**: remove gateway cron disable call. Set
`enabled: false` in registry only.

**`transport/server.py` — `_captain_status`**: read from registry + check task liveness
via `/api/spawn/{task_id}` instead of gateway cron listing.

**`transport/server.py` — new `_dispatch_captain_checkin()`**: helper that calls
`dispatch()` into `member-raven` slot, stores `current_task_id` in registry.

**`transport/server.py` — new `_steer_captain_checkin()`**: helper that calls
`/continue` on `current_task_id`, updates `current_task_id` in registry. Falls back to
`_dispatch_captain_checkin()` on `conversation_gone`.

**`transport/server.py` — new `_captain_timer_loop()`**: background async task that wakes
at `next_fire_at` for each enabled captain entry and calls `_steer_captain_checkin()`.
Runs alongside the existing idle-monitor loop.

**`transport/lifecycle.py` — `_reseed_crew_schedules`**: captain-type entries skip
`POST /api/crons`. Instead check task liveness; re-dispatch if dead.

**`transport/captain.py` — `_CAPTAIN_CHECKIN_TASK`**: remove "persistent session" /
cron context references. Task is now a standard member dispatch.

**`tests/unit/test_captain.py`**: update for new flow.

## What does NOT change

- `schedule()` tool — unaffected, still uses `POST /api/crons` for user-facing cron jobs
- The captain mailbox (`captain@localhost`) — unchanged
- `fire_immediately` behaviour — still fires Raven immediately on first order
- `captain(action="order")` API surface — unchanged

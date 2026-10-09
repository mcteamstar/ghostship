# Tasks: TRN-214

## 1. Registry schema

- [x] 1.1 Add `type: "captain"` field to captain schedule entries in `_captain_do_order`
- [x] 1.2 Add `current_task_id: str | None` field to captain registry entries
- [x] 1.3 Add `next_fire_at: float` field (already present, verify it's set correctly)
- [x] 1.4 Remove `job_id` dependency from captain entries (keep for `schedule()` non-captain entries)

## 2. `_captain_do_order` — replace cron with dispatch

- [x] 2.1 Remove `POST /api/crons` call and all cron body construction
- [x] 2.2 Remove `_captain_checkin_job` / `enabled_job` cron-inspection logic
- [x] 2.3 Add `_dispatch_captain_checkin(crew, crew_id, model)` helper:
  - calls `_resolve_dispatch_slot` to get `member-raven` slot
  - calls `POST /api/spawn` with `_CAPTAIN_CHECKIN_TASK`, `agent=raven`, `keep=True`,
    `parent_session=dashboard:member-raven`
  - returns `task_id`
- [x] 2.4 Write registry entry with `type="captain"`, `current_task_id`, `next_fire_at`,
  `interval_secs`/`cron_expr`, `enabled=True`
- [x] 2.5 For `fire_immediately` path: call `_dispatch_captain_checkin()` directly
- [x] 2.6 For resume path (captain already has `current_task_id`): call
  `_steer_captain_checkin()` which handles liveness check

## 3. `_steer_captain_checkin()` helper

- [x] 3.1 Add `_steer_captain_checkin(crew, crew_id)` helper:
  - reads `current_task_id` from registry
  - calls `POST /api/spawn/{task_id}/continue` with `{"task": _CAPTAIN_CHECKIN_TASK}`
  - on success: updates `current_task_id` in registry, updates `next_fire_at`
  - on `conversation_gone` (404): falls back to `_dispatch_captain_checkin()`
  - on `conversation_busy` (409): logs warning, skips this tick, updates `next_fire_at`
  - on other error: logs warning, updates `next_fire_at` (don't stop the loop)

## 4. `_captain_timer_loop()` — new background task

- [x] 4.1 Add `def _captain_monitor()` alongside the idle-monitor loop (in monitors.py)
- [x] 4.2 Loop: scan registry for captain entries where `enabled=True` and
  `next_fire_at <= now()`
- [x] 4.3 For each due entry: call `_steer_captain_checkin()` (imports from server at call time)
- [x] 4.4 Sleep until the next earliest `next_fire_at` across all crews
  (or a default poll interval of 30s if no entries)
- [x] 4.5 Wire loop into transport startup alongside idle-monitor

## 5. `_captain_stop` — remove gateway cron calls

- [x] 5.1 Remove `GET /api/crons` + `POST /api/crons/{id}/enable` calls
- [x] 5.2 Set `enabled: false` in registry only
- [x] 5.3 Update `_captain_status` to read from registry + `/api/spawn/{task_id}`
  instead of gateway cron listing

## 6. `_reseed_crew_schedules` — captain branch

- [x] 6.1 Detect captain entries (`type == "captain"`) in the registry
- [x] 6.2 For captain entries: skip `POST /api/crons`
- [x] 6.3 Check `current_task_id` liveness via `GET /api/spawn/{task_id}`
- [x] 6.4 If `conversation_gone` or no `current_task_id`: call `_dispatch_captain_checkin()`
- [x] 6.5 If task still running: do nothing (timer loop will fire when due)

## 7. `_CAPTAIN_CHECKIN_TASK` cleanup

- [x] 7.1 Remove references to "persistent session" / cron context from the task prompt
- [x] 7.2 Keep standing orders mailbox reference and all substantive content unchanged

## 8. Unit tests

- [x] 8.1 `_captain_do_order` dispatches into member-raven slot (no cron call)
- [x] 8.2 `_steer_captain_checkin` updates `current_task_id` after /continue
- [x] 8.3 `_steer_captain_checkin` falls back to dispatch on `conversation_gone`
- [x] 8.4 `_steer_captain_checkin` skips tick on `conversation_busy`
- [x] 8.5 `_captain_stop` sets registry `enabled=False` without touching gateway crons
- [x] 8.6 `_reseed_crew_schedules` captain branch re-dispatches on dead task

## 9. Integration test + deploy

- [ ] 9.1 Launch fresh crew, issue captain order, verify Raven dispatches Ghost
  (no `member_identity_unavailable`)
- [ ] 9.2 Verify `captain(action="stop")` stops firing
- [ ] 9.3 Verify container restart reseeds correctly
- [ ] 9.4 Commit and push on `release/0.6.0`
- [ ] 9.5 Bump adjutant submodule, deploy to starport
- [ ] 9.6 Run full smoke test on starport

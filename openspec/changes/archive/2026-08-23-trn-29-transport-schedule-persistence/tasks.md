## 1. crews.json schema + registry helpers

- [x] 1.1 Add `_get_crew_schedules(reg, crew_id) -> list` helper — returns the schedules list for a crew, defaulting to `[]`
- [x] 1.2 Add `_upsert_crew_schedule(reg, crew_id, job) -> None` — insert or update a schedule entry by `job_id`
- [x] 1.3 Add `_remove_crew_schedule(reg, crew_id, job_id) -> None` — remove a schedule entry by `job_id`
- [x] 1.4 Add `_advance_next_fire_at(job: dict) -> None` — mutates `next_fire_at` based on `interval_secs` or next cron tick

## 2. captain() writes to registry

- [x] 2.1 After writing to gateway cron API, write schedule entry to registry via `_upsert_crew_schedule`
- [x] 2.2 On `captain(action="stop")`, set `enabled=False` in registry entry (do not remove)
- [x] 2.3 On `captain(action="order")` resume of paused job, update registry entry with new `next_fire_at`

## 3. schedule list/cancel reads from registry

- [x] 3.1 `schedule(action="list")` — read from registry instead of proxying gateway; fall back to gateway if no registry entries exist (backward compat for pre-TRN-29 crews)
- [x] 3.2 `schedule(action="cancel")` — remove from registry AND cancel in gateway (if crew is running)
- [x] 3.3 `schedule(action="create")` — write to gateway AND registry

## 4. _schedule_monitor loop

- [x] 4.1 Add `_schedule_monitor()` function — daemon thread, polls every 30s
- [x] 4.2 For each due job (`next_fire_at <= now`), call `_ensure_crew_running`
- [x] 4.3 Fire the tick via `POST /api/spawn` with the job's agent and message
- [x] 4.4 Advance `next_fire_at` in registry after successful fire
- [x] 4.5 On failure (crew won't start, gateway error), advance `next_fire_at` and log error
- [x] 4.6 Start `_schedule_monitor` thread alongside `_idle_monitor` at startup

## 5. _reconcile_registry re-seeding

- [x] 5.1 Add `_reseed_crew_schedules(podman, crew_id, crew_info)` helper
- [x] 5.2 For each job in registry schedules, check if it exists in gateway (`GET /api/crons`); if not, re-register it
- [x] 5.3 Call `_reseed_crew_schedules` from `_reconcile_registry` after a crew is successfully restarted

## 6. delay migration: dispatch → schedule

- [x] 6.1 Remove `delay` parameter from `dispatch()` tool
- [x] 6.2 Add `delay` parameter to `schedule()` tool alongside `interval` and `cron`
- [x] 6.3 `schedule(delay=N)` creates a one-shot job: compute fire-at timestamp, write to registry, register in gateway
- [x] 6.4 Update `schedule` tool docstring and README tools table
- [x] 6.5 Update `dispatch` tool docstring to remove delay references
- [x] 6.6 Update `transport://jobs` resource to include `delay`-type jobs from registry

## 7. Tests

- [x] 7.1 Test: `captain(action="order")` writes schedule entry to registry
- [x] 7.2 Test: `schedule(action="list")` returns registry entries when crew stopped
- [x] 7.3 Test: `schedule(action="cancel")` removes from registry
- [x] 7.4 Test: `_schedule_monitor` wakes stopped crew and fires tick
- [x] 7.5 Test: `_schedule_monitor` skips tick and advances when crew won't start
- [x] 7.6 Test: `_reseed_crew_schedules` re-registers missing jobs in gateway
- [x] 7.7 Test: `schedule(delay=N)` creates one-shot entry in registry
- [x] 7.8 Test: `dispatch` no longer accepts `delay` parameter

## 8. Validation

- [x] 8.1 Run targeted tests: `python -m unittest transport.test_transport.SchedulePersistenceTests transport.test_transport.ScheduleMonitorTests -v`
- [x] 8.2 Run `openspec validate --specs`
- [x] 8.3 Run full local test suite, confirm all pass

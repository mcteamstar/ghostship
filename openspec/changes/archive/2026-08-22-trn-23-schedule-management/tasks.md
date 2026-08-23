## 1. Schedule Tool Actions

- [x] 1.1 Add `action` parameter to `schedule()` with values `"create"` (default), `"cancel"`, `"list"` and route to handler functions
- [x] 1.2 Implement `_schedule_cancel(job_id, crew_id)` — call `DELETE /api/crons/{job_id}` on the crew gateway, guard against captain job name, return success/error dict
- [x] 1.3 Implement `_schedule_list(crew_id)` — call `GET /api/crons` on the crew gateway, normalize response into `{"jobs": [...]}` with job_id, name, schedule, agent, enabled, last_run fields
- [x] 1.4 Update `schedule()` docstring and type annotations to document the new action parameter and action-specific arguments

## 2. Dispatch Delayed Fire

- [x] 2.1 Add `fire_after_secs: int | None = None` parameter to `dispatch()`
- [x] 2.2 When `fire_after_secs` is set, validate >= 1 and create a one-shot cron job via `POST /api/crons` with `delay` set to `fire_after_secs` and `strict_schedule=True`, instead of the immediate spawn
- [x] 2.3 Return `{"job_id": ..., "status": "delayed", "fire_after_secs": N, ...}` for delayed dispatches (no `task_id` since spawn hasn't happened yet)
- [x] 2.4 Update `dispatch()` docstring to document the `fire_after_secs` parameter

## 3. transport://jobs Resource

- [x] 3.1 Add `@mcp.resource("transport://jobs", ...)` decorator and `resource_jobs()` function that iterates all tracked crews
- [x] 3.2 For each running crew, call `GET /api/crons` and collect jobs with crew_id, job_id, name, schedule, agent, enabled, last_run, last_status
- [x] 3.3 Format output as grouped plain text (one section per crew) matching the `transport://agents` style
- [x] 3.4 Handle crew connection errors gracefully — report inline rather than failing the resource read

## 4. Tests

- [x] 4.1 Add test for `schedule(action="cancel", ...)` — success case and not-found case
- [x] 4.2 Add test for `schedule(action="cancel", ...)` refusing to cancel the captain check-in job
- [x] 4.3 Add test for `schedule(action="list", ...)` — with jobs and empty case
- [x] 4.4 Add test for `dispatch(fire_after_secs=300)` — verify cron job creation with delay parameter
- [x] 4.5 Add test for `dispatch(fire_after_secs=0)` — verify validation error
- [x] 4.6 Add test for `resource_jobs()` — mock crew API responses and verify aggregated output

## 5. Documentation

- [x] 5.1 Update README tools table with new `schedule` actions (cancel, list) and `dispatch` fire_after_secs parameter
- [x] 5.2 Add `transport://jobs` to the resources section of the README

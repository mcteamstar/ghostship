## 1. Dry-run: surface scheduled jobs

- [x] 1.1 In `nuke()` dry-run path (`confirm=False`), load registry schedules for the crew using `_get_crew_schedules(reg, crew_id)` (read `reg` from `_load_registry()` under `_registry_lock` before the existing active-task query)
- [x] 1.2 Extend the dry-run return dict to include `scheduled_jobs: len(schedules)` and `scheduled_job_names: [s.get("name", "") for s in schedules]`
- [x] 1.3 Verify that `scheduled_jobs: 0` and `scheduled_job_names: []` are returned when the crew has no schedule entries

## 2. Confirmed nuke: cancel gateway cron jobs

- [x] 2.1 In `nuke()` confirmed path (`confirm=True`), before calling `_cleanup_crew(...)`, read the crew's schedule entries from the registry using `_get_crew_schedules(reg, crew_id)` (acquire `_registry_lock` for the read, then release before issuing HTTP calls)
- [x] 2.2 For each schedule entry, issue `_crew_api(crew, "DELETE", f"/api/crons/{job_id}")` wrapped in a `try/except Exception` block; on failure log at `WARNING` level with `logger.warning("nuke: failed to cancel cron %s for crew %s: %s", job_id, crew_id, e)` and continue iterating
- [x] 2.3 Ensure the cancellation loop uses bare `_crew_api` (not `_crew_api_with_recovery`) to avoid an unwanted container restart before teardown

## 3. Tests

- [x] 3.1 Add a unit test for the dry-run path: a crew with two schedule entries in the registry returns `scheduled_jobs: 2` and both names in `scheduled_job_names`
- [x] 3.2 Add a unit test for the dry-run path: a crew with no schedule entries returns `scheduled_jobs: 0` and `scheduled_job_names: []`
- [x] 3.3 Add a unit test for the confirmed-nuke path: verifies `DELETE /api/crons/<id>` is called for each schedule entry before `_cleanup_crew` is invoked
- [x] 3.4 Add a unit test for confirmed-nuke with a failing gateway `DELETE`: verify the exception is caught, a WARNING is logged, and `_cleanup_crew` is still called (teardown not blocked)
- [x] 3.5 Add a unit test for confirmed-nuke with no schedule entries: verify no `DELETE` calls are issued and teardown proceeds normally

## 4. Spec sync

- [x] 4.1 Run `openspec validate --store repo` and confirm no errors on the change

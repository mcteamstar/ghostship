## 1. Core fix — _schedule_monitor in lifecycle.py

- [ ] 1.1 After `_ensure_crew_running` succeeds, add a gateway `/api/crons` fetch via `_crew_api(crew, "GET", "/api/crons")` to look up the matching job by `sched["job_id"]`
- [ ] 1.2 If the gateway job is found with `enabled: false`, log at INFO, write `enabled: false` back to the registry entry under `_registry_lock`, and `continue` to skip firing
- [ ] 1.3 Wrap the gateway fetch in a `try/except` — on any exception, log at WARNING and fall through to fire (fail-open), preserving the existing behaviour when the gateway is unreachable
- [ ] 1.4 Keep the existing `sched.get("enabled", True)` check at the top of the loop as a fast-path skip for jobs already synced as disabled in the registry (no wake needed for known-disabled jobs)

## 2. Registry write-back

- [ ] 2.1 In the write-back path (step 1.2), reload the registry with `_load_registry()` under `_registry_lock`, find the matching entry by `job_id`, set `enabled = False`, and call `_save_registry(reg)` — matching the pattern in `_reseed_cron_jobs`

## 3. Unit tests in tests/unit/test_lifecycle.py

- [ ] 3.1 Test: schedule monitor skips firing when gateway reports `enabled: false` — mock `_crew_api` to return a cron payload with `enabled: false` for the matching job; assert spawn is not called and registry is updated to `enabled: false`
- [ ] 3.2 Test: schedule monitor fires normally when gateway reports `enabled: true` — mock `_crew_api` to return a cron payload with `enabled: true`; assert spawn is called
- [ ] 3.3 Test: schedule monitor fires normally when job is absent from gateway cron listing (gateway knows nothing about this job_id) — mock `/api/crons` to return an empty jobs list; assert spawn is called (fail-open)
- [ ] 3.4 Test: schedule monitor falls back to registry `enabled` and skips when gateway fetch raises and registry has `enabled: false` — mock `_crew_api` raising an exception and registry `enabled: false`; assert spawn is not called
- [ ] 3.5 Test: schedule monitor fires when gateway fetch raises and registry has `enabled: true` (or field absent) — assert spawn is called (fail-open fallback to registry)

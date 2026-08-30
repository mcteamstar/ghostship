## 1. Reconcile pass in `_reseed_cron_jobs`

- [ ] 1.1 At the top of `_reseed_cron_jobs`, after fetching `gateway_jobs`, build a map of `job_id → gateway_job` from the gateway response
- [ ] 1.2 For each registry schedule entry whose `job_id` exists in the gateway map: update its `enabled` field to match `gateway_job.get("enabled", True)`; also update `interval_secs` and `cron_expr` if they differ
- [ ] 1.3 Remove registry schedule entries whose `job_id` is absent from the gateway map (job was deleted inside the container)
- [ ] 1.4 Write the updated registry to disk under `_registry_lock` via `_save_registry` after the reconcile pass
- [ ] 1.5 The existing reseed loop runs unchanged after the reconcile pass — it now only registers jobs truly missing from the gateway

## 2. Unit tests

- [ ] 2.1 Test: gateway reports job with `enabled: false` → registry entry updated to `enabled: false`, job not re-registered
- [ ] 2.2 Test: gateway does not include a job that exists in registry → registry entry removed
- [ ] 2.3 Test: gateway is missing a job that exists in registry with `enabled: true` → job registered in gateway (existing reseed behaviour)
- [ ] 2.4 Test: gateway `/api/crons` returns an error → both reconcile and reseed passes skipped, registry unchanged

## 3. Verification

- [ ] 3.1 Run `bash tests/run.sh --unit` — all tests pass
- [ ] 3.2 Run `bash tests/run.sh --integration` — all tests pass

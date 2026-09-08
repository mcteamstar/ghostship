## 1. lifecycle.py — _ensure_crew_running active-limit fix

- [x] 1.1 In the `GA_MAX_ACTIVE_CREWS > 0` block in `_ensure_crew_running`, refactor the counting logic: acquire lock → load registry snapshot → release lock → iterate snapshot and call `container_is_running` for each `status == "running"` entry outside the lock → exclude non-running entries from the count
- [x] 1.2 Collect registry corrections (entries to flip from `"running"` to `"stopped"`) during the Podman-check loop; re-acquire lock → apply corrections and save → release lock before making the limit decision
- [x] 1.3 Write unit tests for `_ensure_crew_running` covering: (a) stale running entry excluded from limit count, (b) stale entry corrected to stopped in registry, (c) limit enforced correctly after stale entries are excluded

## 2. server.py — crews() active_crews fix

- [x] 2.1 In the `crews()` handler, for each entry whose registry `status` is `"running"`, call `container_is_running` before the `_probe_gateway` call and before `container_inspect` for uptime; if the container is not actually running, skip both the gateway probe and the uptime inspect, set the entry's `status` to `"stopped"`, set `gateway_healthy` to `false`, and add the entry to the corrections list
- [x] 2.2 After building the result list, write all registry corrections (running→stopped mismatches) back under `_registry_lock` in a single save call (second acquisition, following the established reconcile pattern)
- [x] 2.3 Compute `active_crews` from the corrected result (count of entries actually confirmed running by Podman)
- [x] 2.4 Write unit tests for `crews()` covering: (a) `active_crews` excludes a registered-running crew whose container is stopped, (b) per-crew `status` reports `"stopped"` for that crew in the response, (c) `_probe_gateway` is NOT called for that crew, (d) registry is written back with the corrected status, (e) `active_crews` matches confirmed-running count

## 3. Validation

- [x] 3.1 Run the full unit test suite (`tests/unit/`) and confirm all tests pass
- [x] 3.2 Run `openspec validate --change trn-132-stale-active-crews-count` and confirm no errors

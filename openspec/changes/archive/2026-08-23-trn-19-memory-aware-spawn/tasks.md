## 1. PodmanClient API extension

- [ ] 1.1 Add `system_info()` method to `PodmanClient` that calls `GET /libpod/system/info` and returns the parsed JSON response
- [ ] 1.2 Add `_get_host_memory_gb(podman)` module-level function that extracts `host.memFree` from `system_info()` and converts bytes to GB (float, 1 decimal)

## 2. Memory wait gate

- [ ] 2.1 Add `_wait_for_memory(podman, required_gb, timeout_secs)` function implementing the 5-second poll loop that returns current free GB
- [ ] 2.2 Integrate `_wait_for_memory` into `_ensure_crew_running` — call it before `container_start()` when the container is stopped; raise `RuntimeError` with the specified error message format on timeout
- [ ] 2.3 Read `GA_MIN_FREE_MEM_GB` (default 2.0) and `GA_MEMORY_WAIT_SECS` (default 60) from environment at module level
- [ ] 2.4 Skip the memory gate when `GA_MIN_FREE_MEM_GB == 0`

## 3. Config patch tuning

- [ ] 3.1 Read `GA_SPAWN_MIN_MEMORY_GB` (default 1.5) from environment and use it in `_patch_crew_config` instead of hardcoded `0`
- [ ] 3.2 Read `GA_RESOURCE_PRESSURE_GB` (default 2.0) and `GA_RESOURCE_CRITICAL_GB` (default 1.0) from environment and patch them instead of hardcoded `0`

## 4. crews() memory field

- [ ] 4.1 Add `_get_host_memory_gb_cached(podman)` with 5-second TTL cache (module-level tuple of `(monotonic_timestamp, value)`)
- [ ] 4.2 Add `host_memory_available_gb` field to `crews()` response using the cached reader; set to `null` on Podman info failure

## 5. Tests

- [ ] 5.1 Create `FakePodmanClient` test helper in `test_transport.py` with configurable `system_info()` return values
- [ ] 5.2 Test: memory available immediately — gate passes, no sleep
- [ ] 5.3 Test: memory frees after 2 polls — gate passes after ~10s simulated wait
- [ ] 5.4 Test: timeout expires — `RuntimeError` raised with correct message format
- [ ] 5.5 Test: `GA_MIN_FREE_MEM_GB=0` — gate is skipped entirely
- [ ] 5.6 Test: `_patch_crew_config` writes `GA_SPAWN_MIN_MEMORY_GB` value (not hardcoded 0)
- [ ] 5.7 Test: `crews()` response includes `host_memory_available_gb` field
- [ ] 5.8 Test: cache TTL — second call within 5s does not invoke `system_info()` again

## 6. Documentation

- [ ] 6.1 Document `GA_SPAWN_MIN_MEMORY_GB`, `GA_MIN_FREE_MEM_GB`, `GA_MEMORY_WAIT_SECS` in `docs/configuration.md`
- [ ] 6.2 Add env var descriptions to `install.sh` comments

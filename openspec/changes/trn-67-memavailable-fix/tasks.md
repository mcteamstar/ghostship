## 1. Fix `/proc/meminfo` read in transport/server.py

- [ ] 1.1 Locate the `/proc/meminfo` parsing code in `transport/server.py`
- [ ] 1.2 Change the key read from `MemFree` to `MemAvailable`, with a fallback to `MemFree` if `MemAvailable` is absent (kernel < 3.14 defensive guard)
- [ ] 1.3 Confirm the fix applies to both the memory gate (spawn check) and the `host_memory_available_gb` field in the `crews()` response — update both if they are separate reads

## 2. Update docs

- [ ] 2.1 In `docs/configuration.md`, update the `GA_MIN_FREE_MEM_GB` description to clarify it compares against `MemAvailable` (not `MemFree`)

## 3. Verification

- [ ] 3.1 On a Linux host (or WSL), call `crews()` and confirm `host_memory_available_gb` now matches `MemAvailable` from `/proc/meminfo` (not `MemFree`)
- [ ] 3.2 Confirm the spawn gate no longer fires spuriously when `MemAvailable` is > `GA_MIN_FREE_MEM_GB` but `MemFree` is low
- [ ] 3.3 Run the transport test suite and confirm all tests pass

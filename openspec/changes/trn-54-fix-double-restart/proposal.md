## Why

`_ensure_crew_running` performs three container lifecycle transitions per idle-crew wake (start → wait → patch_config → stop → start → wait), adding up to 90 seconds of latency on every crew wake-up. The extra stop/start cycle exists solely to work around a KiroCrew bug where `spawn_min_memory_gb` is not read from config files — but the config patch and bounce are only necessary if the gateway has not yet applied the patched value. On a plain restart the config can be patched before the gateway starts, eliminating the second cycle entirely.

## What Changes

- `_ensure_crew_running`: patch crew config **before** the initial `container_start` call, so the gateway boots with the correct config already on disk. Remove the redundant `container_stop` / `container_start` / `_wait_gateway` cycle that follows the first start.
- The WORKAROUND comment is retained and updated to reflect the new ordering — the workaround is still in place, just applied more efficiently.
- One additional `_wait_gateway` call removed from the hot path, reducing worst-case wake latency by ~30–45 s.

## Capabilities

### New Capabilities
<!-- None -->

### Modified Capabilities
- `idle-and-recovery`: The transparent-restart scenario now specifies that config patching happens before the container starts, not after, and that only a single start/wait cycle is performed.

## Impact

- `transport/server.py`: `_ensure_crew_running` — remove one `container_stop` + `container_start` + `_wait_gateway` call
- Tests: update or add unit tests covering the restart path to assert `container_start` is called exactly once per wake cycle
- No API or behaviour change visible to callers — the crew is ready at the same point, just faster

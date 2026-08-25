## Why

`_ensure_crew_running` currently wakes a stopped crew with `container_start` → `_wait_gateway` → config patch → `container_stop` → `container_start` → `_wait_gateway`. The first gateway wait only makes the container available for the exec-based configuration patch; the workaround then stops and starts the container again. Because `_patch_crew_config` uses `podman exec`, it cannot be applied while the container is stopped. Removing that provisional wait preserves the feasible workaround while eliminating up to 30 seconds of unnecessary latency on every crew wake.

## What Changes

- `_ensure_crew_running` starts the stopped container without waiting, applies the configuration patch through exec, stops it, starts it again, and performs the single readiness wait on the final start.
- The WORKAROUND comment is retained and explicitly documents the provisional-start, exec-patch, stop, final-start, and wait sequence.
- One unnecessary `_wait_gateway` call is removed from the hot path without changing the required configuration bounce or externally visible recovery behavior.

## Capabilities

### New Capabilities
<!-- None -->

### Modified Capabilities
- `idle-and-recovery`: The transparent-restart scenario now specifies that the exec-based configuration patch is applied after a provisional start and before the final restart, with exactly one gateway wait and no wait on the provisional start.

## Impact

- `transport/server.py`: `_ensure_crew_running` — remove the first `_wait_gateway` call while retaining the configuration patch and its stop/start bounce.
- Tests: assert that the normal stopped-container path calls `container_start` exactly twice and `_wait_gateway` exactly once per wake cycle.
- No API or behavior change is visible to callers — the crew is ready at the same point, just faster.

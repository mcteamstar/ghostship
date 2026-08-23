## Why

Ghostship runs on hosts with dynamic memory allocation — HyperV ballooning on
a dedicated Podman machine VM on macOS. The hypervisor targets 20% free memory and
adjusts the guest's visible RAM dynamically, but it cannot react instantly to
sudden spikes.

Currently `spawn_min_memory_gb` is patched to `0` in every crew's `config.json`
as a workaround for KiroCrew's default `4.0` GB threshold being too greedy on
12-13 GB hosts where two active crews already consume ~7.8 GB. This leaves no
safety net — OOM kills are happening mid-task (observed: Spectre OOM during
TRN-3 implementation run, 2026-08-22).

The right fix is to work with the balloon, not against it:

1. Raise `spawn_min_memory_gb` from `0` to a value that respects actual host
   constraints (not `4.0`, which is calibrated for machines with 16+ GB)
2. Add a transport-level pre-launch memory check that waits for the balloon to
   deflate before starting a new container — giving the hypervisor time to
   respond rather than hammering a cold spawn into a memory-pressured host

## What Changes

### 1. KiroCrew threshold tuning in `_patch_crew_config`

The post-restart hook currently patches `spawn_min_memory_gb: 0`. Replace with
a configurable value via `GA_SPAWN_MIN_MEMORY_GB` (default `1.5`). Also tune
adjacent fields:

| Field | Current (patched) | Proposed | Rationale |
|:------|:-----------------|:---------|:----------|
| `spawn_min_memory_gb` | 0 | 1.5 | Headroom for balloon + KiroCrew's own admission gate |
| `resource_pressure_gb` | 4.0 (default, unpatched) | 2.0 | Realistic for 12 GB host |
| `resource_critical_gb` | 2.0 (default, unpatched) | 1.0 | Hard floor before OOM |

### 2. Transport pre-launch memory check in `_ensure_crew_running`

Before starting a stopped container, poll `podman info` for host `MemFree`.
If below `GA_MIN_FREE_MEM_GB` (default `2.0` GB), wait up to
`GA_MEMORY_WAIT_SECS` (default `60`) in 5-second increments for the balloon
to deflate. If memory doesn't free up within the timeout, return a clear
error: `"Insufficient host memory to start crew <id>: <N>GB free, <T>GB
required. Retry in a moment."` — not an OOM crash.

### 3. New config vars

- `GA_SPAWN_MIN_MEMORY_GB` (default `1.5`) — patched into `spawn_min_memory_gb`
- `GA_MIN_FREE_MEM_GB` (default `2.0`) — transport pre-launch check threshold
- `GA_MEMORY_WAIT_SECS` (default `60`) — maximum wait before returning an error

### 4. `crews()` includes `host_memory_available_gb`

Add a top-level field to the `crews()` response (alongside the crew list) so
the Admiral can see current host memory state without SSH.

## Capabilities

### Modified Capabilities
- `crew-lifecycle`: pre-launch memory check with backoff; `spawn_min_memory_gb`
  now configurable via env var instead of hardcoded 0
- `mcp-server`: `crews()` gains `host_memory_available_gb` field

## Decisions

- `GA_MIN_FREE_MEM_GB: 2.0` as the transport threshold — leaves headroom for
  the balloon to react while still allowing launches on a busy host
- `GA_SPAWN_MIN_MEMORY_GB: 1.5` as the KiroCrew admission threshold — below
  the transport check (2.0) so KiroCrew's gate never triggers before the
  transport's; transport is the outer guard
- Wait-then-error approach over immediate failure — gives balloon 60s to respond
  before giving up; most balloon adjustments happen within 5-15s
- `resource_pressure_gb: 2.0` and `resource_critical_gb: 1.0` — govern
  KiroCrew's internal subagent spawning within a crew. At rest on a 12 GB host
  with 2 active crews (~7.8 GB used), ~4 GB is free — above both thresholds.
  At peak (8 GB used) ~4 GB free — still above. These values are safe for
  the current host profile.
- `podman info MemFree` on macOS reports VM memory (the podman machine guest),
  not physical host memory. This is the correct value for container spawn
  decisions — container spawning is bounded by VM memory, not host RAM. Error
  messages should say "available memory" rather than "host memory" to be
  accurate on both Linux and macOS.
- `host_memory_available_gb` in `crews()` calls `podman info` on each request.
  Cache the value for 5 seconds to avoid per-call Podman API overhead.

## Known Limitations

- **TOCTOU on concurrent launches** — two simultaneous `launch()` calls can
  both pass the memory check at the same instant, each seeing sufficient free
  memory, and together exceed available RAM. This is a known race condition
  accepted for v1. The balloon and KiroCrew's own admission gate provide a
  secondary backstop; a per-launch serialisation lock is a future improvement.

## Open Questions

- Should `GA_MIN_FREE_MEM_GB` be exposed in `install.sh` as a flag, or just
  as a documented env var? The default should be fine for most users.

## Impact

- `transport/server.py` — `_patch_crew_config`, `_ensure_crew_running`, `crews()`
- `transport/test_transport.py` — tests for pre-launch check and backoff
- `install.sh` — document new env vars
- `docs/configuration.md` — document `GA_SPAWN_MIN_MEMORY_GB`, `GA_MIN_FREE_MEM_GB`,
  `GA_MEMORY_WAIT_SECS`

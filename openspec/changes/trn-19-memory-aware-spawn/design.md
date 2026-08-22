## Context

See proposal.md — Why. The transport layer (`server.py`) manages crew container
lifecycles via `_ensure_crew_running`. Today it restarts stopped containers with
no regard for host memory pressure. The `_patch_crew_config` function hardcodes
`spawn_min_memory_gb=0`, disabling KiroCrew's internal memory gate entirely.

The host uses HyperV balloon memory — the hypervisor can deflate the balloon
within 5–15 seconds when pressure rises, but the transport must give it time.

## Goals / Non-Goals

**Goals:**
- Add a memory-check gate to `_ensure_crew_running` that waits for the balloon
  to deflate before starting containers
- Make all memory thresholds configurable via environment variables
- Expose host memory state in the `crews()` API response
- Provide testability hooks so the memory gate can be exercised in unit tests
  without a real Podman socket

**Non-Goals:**
- Solving the TOCTOU race on concurrent launches (accepted for v1)
- Adding a per-launch serialisation lock
- Changing KiroCrew's upstream `AgentConfig` loader

## Decisions

### 1. Podman info API for memory reading

**Choice:** Add a `system_info()` method to `PodmanClient` that calls
`GET /libpod/system/info` and extracts `host.memFree` from the response.

**Alternatives considered:**
- Reading `/proc/meminfo` inside the transport process — would report the VM's
  own view but bypasses Podman's reporting layer. Rejected because on macOS the
  transport runs on the host while containers run in the Podman machine VM;
  `/proc/meminfo` would be wrong.
- `podman stats` — reports per-container usage, not host-level free memory.

**Rationale:** `podman info` reports the Podman machine VM's memory on macOS and
the host's memory on Linux — both are the correct context for spawn decisions
since containers are bounded by that memory pool.

### 2. Wait/retry loop structure

```python
def _wait_for_memory(podman: PodmanClient, required_gb: float, timeout_secs: int) -> float:
    """Block until host has required_gb free, or timeout_secs expires.
    Returns current free GB (may be < required_gb on timeout).
    """
    deadline = time.monotonic() + timeout_secs
    while True:
        free_gb = _get_host_memory_gb(podman)
        if free_gb >= required_gb:
            return free_gb
        if time.monotonic() >= deadline:
            return free_gb
        time.sleep(5)
```

The loop polls every 5 seconds — matching the hypervisor's typical balloon
reaction time (5–15s) without excessive API calls. The 5-second cache on
`_get_host_memory_gb` is bypassed inside the wait loop (each iteration needs a
fresh reading).

### 3. Testability hooks

**Choice:** Extract memory-reading into a module-level function
`_get_host_memory_gb(podman)` that calls `podman.system_info()`. Tests monkey-
patch this function or inject a mock `PodmanClient` with a fake `system_info()`
return value.

The `PodmanClient.system_info()` method is a thin wrapper over a single HTTP
call, making it trivial to mock:

```python
def system_info(self) -> dict:
    return self._req("GET", "/libpod/system/info")
```

For unit tests, provide a `FakePodmanClient` that returns configurable
`memFree` values from `system_info()`, allowing tests to simulate:
- Memory available immediately
- Memory appearing after N polls
- Timeout with memory never freeing

### 4. Integration point in _ensure_crew_running

The memory check runs **before** `podman.container_start()` — after confirming
the container is stopped but before actually starting it. This placement ensures:
- Already-running containers skip the check (fast path unchanged)
- The serialisation Event still protects concurrent restart attempts
- The wait loop happens while holding the leader role, so waiters also benefit

### 5. Cached memory for crews() response

A module-level `_host_memory_cache: tuple[float, float] | None` stores
`(timestamp, value_gb)`. `_get_host_memory_gb_cached(podman)` returns the
cached value if `time.monotonic() - timestamp < 5.0`, otherwise refreshes.
The wait loop calls an uncached variant directly.

### 6. Environment variable parsing

All three env vars are read at module import time via `float(os.environ.get(...))`
with defaults. This matches the existing pattern in `server.py` for other
`GA_*` configuration (e.g., `GA_AUTO_STOP_HOURS`).

## Risks / Trade-offs

- **[TOCTOU on concurrent launches]** → Accepted for v1. The per-crew Event
  serialises restarts for the same crew; cross-crew races are mitigated by
  the balloon + KiroCrew's internal admission gate.
- **[5-second poll interval]** → Could delay launches by up to 4.9s after
  memory frees. Acceptable given the alternative is an OOM crash.
- **[Podman info latency]** → `podman info` takes ~50ms on the local socket.
  12 calls over 60s max wait is negligible overhead.
- **[Cache staleness for crews()]** → A 5-second cache means the reported
  value can be slightly stale. Acceptable for a diagnostic field.

## Migration Plan

1. Deploy updated `server.py` — new env vars use safe defaults, so no config
   changes are required for existing installs.
2. Remove `spawn_min_memory_gb=0` workaround documentation once verified.
3. Optionally tune `GA_MIN_FREE_MEM_GB` / `GA_SPAWN_MIN_MEMORY_GB` per host.

No rollback risk: the old behavior is equivalent to `GA_MIN_FREE_MEM_GB=0`
(gate disabled).

## Why

The transport's memory gate reads `MemFree` from `/proc/meminfo` to decide whether to start a crew container. On Linux (including WSL), `MemFree` only counts truly idle pages — it excludes the kernel's buff/cache, which can consume gigabytes that are immediately reclaimable under pressure. The result: the gate fires constantly on any live Linux system, blocking crew starts and reporting misleadingly low memory to the Admiral even when the host has plenty of room.

This was the root cause of ghostship appearing broken on WSL and of `host_memory_available_gb` reporting near-zero on Linux hosts with a large page cache (e.g. 225MB `MemFree` vs 6.4GB `MemAvailable` with 6.5GB in buff/cache).

## What Changes

- Replace `MemFree` with `MemAvailable` in the transport's `/proc/meminfo` parser — the single-line fix that makes the memory gate reflect reality
- `host_memory_available_gb` in the `crews()` MCP response now reports `MemAvailable` (the accurate figure)
- Update `GA_MIN_FREE_MEM_GB` documentation in `docs/configuration.md` to clarify it compares against `MemAvailable`

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None — this is a Linux-only bug fix with no spec-level behavior changes (`skip_specs: true`).

## Impact

- `transport/server.py` — one-line change: `MemFree` → `MemAvailable` in the `/proc/meminfo` read
- `docs/configuration.md` — clarify `GA_MIN_FREE_MEM_GB` semantics
- Linux and WSL installs only; macOS is unaffected

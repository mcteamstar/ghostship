## Context

See proposal.md for motivation. The transport reads `/proc/meminfo` on Linux to gate crew container starts and to populate `host_memory_available_gb` in the `crews()` response. The current read uses `MemFree`; the fix uses `MemAvailable`.

`/proc/meminfo` format (relevant fields):
```
MemTotal:       11534336 kB
MemFree:          230144 kB
MemAvailable:    6553600 kB
...
```

`MemAvailable` was added in Linux 3.14 (2014) and is present on all supported platforms (Ubuntu 22.04+, WSL2). It is not present on macOS — the transport's memory check is already gated behind a Linux-only code path, so no macOS impact.

## Goals / Non-Goals

**Goals:**
- Memory gate and `host_memory_available_gb` reflect genuinely allocatable memory on Linux
- Fix applies to both the spawn gate and the `crews()` report in one place

**Non-Goals:**
- macOS memory reporting (unaffected — different code path)
- Changing the `GA_MIN_FREE_MEM_GB` default value or the gate logic itself
- Any other changes to the memory subsystem

## Decisions

### D1: Replace `MemFree` with `MemAvailable` at the parse site

**Decision:** Find the single location in `transport/server.py` that parses `/proc/meminfo` and change the key from `MemFree` to `MemAvailable`. One line change.

**Alternatives considered:**
- *Parse both and take the max*: unnecessary complexity; `MemAvailable` is strictly more accurate.
- *Use `psutil`*: adds a dependency for a one-line stdlib fix. Rejected.

**Rationale:** `MemAvailable` is the kernel's own estimate of allocatable memory including reclaimable cache. It is the correct field per `proc(5)` and is what tools like `free -h` display as "available".

## Risks / Trade-offs

- [Risk] `MemAvailable` absent on very old kernels (< 3.14).
  Mitigation: Fall back to `MemFree` if `MemAvailable` key is not found in the parsed dict. Ubuntu 22.04+ and WSL2 are well above 3.14 so this is purely defensive.

## Migration Plan

1. Change `MemFree` → `MemAvailable` (with `MemFree` fallback) in `transport/server.py`
2. Rebuild and restart the transport (`./install.sh` or `./start.sh`)
3. Verify `host_memory_available_gb` in `crews()` response now reflects a sensible value

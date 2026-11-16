# Proposal

## Why

Crew admission currently uses Podman's remote system info and falls back to `memFree` when `memAvailable` is absent. Podman 5.7 on vm23 omits `memAvailable`, so the gate counts only unused pages and rejects wakeups even when Linux reports several gigabytes available after reclaimable cache is considered.

## What Changes

- On Linux, read the kernel's `MemAvailable` value from `/proc/meminfo` for crew admission and memory reporting.
- Keep the existing Podman-info path for non-Linux development hosts.
- Treat an unreadable or malformed Linux memory value as unavailable rather than silently substituting raw `memFree`.
- Add focused tests for parsing, failure handling, and the non-Linux path.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `crew-lifecycle`: specify the platform-appropriate source and meaning of available memory used by the pre-launch memory gate.

## Impact

- `transport/podman.py` memory helpers and their callers in crew admission/reporting.
- Unit tests for memory discovery and admission.
- The `crew-lifecycle` specification. No new dependency or public API is required.

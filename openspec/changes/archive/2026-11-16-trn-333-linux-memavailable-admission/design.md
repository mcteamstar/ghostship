# Design

## Context

See proposal.md - Why. The memory helper in `transport/podman.py` is shared by crew admission and fleet memory reporting. The transport runs in a Linux container on vm23; reading `/proc/meminfo` inside that container returned the host's `MemAvailable`, and the transport container currently has no cgroup memory cap.

## Goals / Non-Goals

**Goals:**
- Use Linux's estimate of memory available to new workloads for admission and reporting.
- Keep the existing Podman info behavior for non-Linux local development.
- Fail closed with an explicit error if the Linux value is unavailable.

**Non-Goals:**
- Change admission thresholds, wait intervals, or crew memory estimates.
- Change Podman installation or add an apt repository.
- Add support for interpreting a transport container memory limit as the crew-host capacity.

## Decisions

- **Read `/proc/meminfo` on Linux.** Parse the `MemAvailable` entry, whose value is reported in kB, convert it to GiB, and retain the existing one-decimal rounding. This avoids Podman 5.7's incomplete remote info fields and uses the kernel's estimate that accounts for reclaimable cache. Continue to use Podman info on non-Linux hosts, preferring `memAvailable` and retaining its existing fallback behavior there.
- **Do not substitute Linux `MemFree`.** If `/proc/meminfo` cannot be read or has no valid `MemAvailable` entry, surface an unavailable-memory error and reject the start. Using `MemFree` would reproduce the incorrect admission decision this change addresses.
- **Keep the existing short cache.** The shared helper's five-second cache remains the single source used by admission and fleet reporting; no additional polling or external process is needed.

## Risks / Trade-offs

- [Container proc view differs on another runtime] → Keep the Linux source isolated behind the memory helper and cover both parsing and fallback paths; verify the running transport continues to see the engine host's value.
- [Malformed or inaccessible proc data blocks starts] → Fail closed with an explicit diagnostic rather than silently admitting work based on an invalid estimate.

## Migration Plan

No host package changes or migration are required. Deploy the transport update; rollback is the normal application rollback, restoring the previous helper behavior.

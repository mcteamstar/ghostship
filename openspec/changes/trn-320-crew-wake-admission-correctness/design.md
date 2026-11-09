# Design

## Context

`ensure_running`'s leader path in `transport/launcher.py` reserves capacity, calls `container_start`, patches config, restarts, waits for the gateway and mints a cookie. Failures after `container_start` raise without stopping the container, and registry status only flips inside `if new_cookie:`. `_check_memory_gate` calls `_wait_for_memory` with live host readings while `_capacity_lock` is held, and ignores `_start_reservations`.

## Goals / Non-Goals

**Goals:**
- Podman state and registry state agree after any wake outcome.
- Admission cannot be passed twice on the same free memory.

**Non-Goals:**
- Measuring real per-crew memory use. A configured estimate is enough.
- Changing the active-crew limit logic, which already counts reservations.

## Decisions

- **Cleanup in a single `try/except` around the post-start steps.** On any exception, best-effort `container_stop`, release the reservation, set registry status `stopped`, then re-raise. Alternative considered: leave the container running and mark the registry running-unhealthy. Rejected because a half-started crew still consumes memory and a slot with nothing able to use it.
- **Treat a failed cookie mint as a failed wake.** A crew without a cookie cannot be driven, so reporting success would mislead waiters.
- **Per-start memory estimate.** Add `GA_START_MEM_ESTIMATE_GB` (default 1.0) and subtract `estimate × len(_start_reservations)` from the live reading in `_check_memory_gate`. Alternative considered: hold the capacity lock until the gateway is ready. Rejected because it serialises all wakes behind 30 to 60 second gateway boots.
- **Release the capacity lock while waiting for memory.** Check, release the lock, sleep, then re-acquire and re-check with the reservation set, instead of a single 60-second wait under the lock.
- **Remove `_run_restart_cycle`.** It has no callers since TRN-316 and its tests exercise a path production no longer uses.

## Risks / Trade-offs

- [The estimate is wrong for heavy compositions] → Configurable, documented in `docs/configuration.md`, and conservative by default.
- [Stopping a container on cookie mint failure loses a crew that might have recovered] → The next call wakes it again through the normal path.

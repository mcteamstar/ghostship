# Design

## Context

See proposal.md for motivation. `CrewLauncher` currently stores the current event, the latest outcome, and the generation counter in separate per-crew maps. A new leader can remove the prior outcome after the old event is signaled but before an old waiter reads it.

## Goals / Non-Goals

**Goals:**
- Keep each waiter bound to the exact restart cycle it joined.
- Preserve success and failure outcomes until all waiters holding that cycle can read them.
- Keep at most one active restart leader per crew and retain concurrency across different crews.

**Non-Goals:**
- Change restart admission, timeout duration, or crew lifecycle semantics.
- Retry or cancel a restart on behalf of a waiter.

## Decisions

- Represent each in-progress restart as one cycle record containing its generation, completion event, and eventual outcome. Waiters capture that record while holding the startup-state lock.
- The leader records the outcome on its cycle record before signaling its event. A new leader may replace the active per-crew record, but cannot mutate the prior record already held by its waiters.
- Let normal object references keep a completed record alive while leader and waiters still hold it, then release it naturally. This avoids a separate outcome-retention map and waiter-count cleanup protocol.
- Alternative considered: key the existing outcome dictionary by `(crew_id, generation)` and add explicit waiter reference counts. Rejected because it creates manual cleanup paths without improving correctness over a per-cycle record.

## Risks / Trade-offs

- [Concurrent tests that rely on internal map shapes may need adjustment] → Keep the public lifecycle API unchanged and test observable leader/waiter outcomes with synchronization barriers.
- [A missing outcome could be confused with an unfinished cycle] → The event remains the completion signal; a signaled record without an outcome is still an explicit error.

## Migration Plan

No persisted data or external API changes are required. The coordinator state is in-memory and rebuilt with the transport process. Rollback is reverting the in-memory coordination representation.

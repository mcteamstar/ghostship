# Design

## Context

The idle monitor currently marks `_stopping` under the registry lock, releases that lock, and calls Podman. Crew recovery uses restart events, but the leader's initial running probe and an early stop occur before the current protected restart body.

## Goals / Non-Goals

**Goals:**
- Serialize state-changing stop and wake transitions per crew.
- Signal each restart waiter with the outcome of its leader, including failures before the restart body.
- Keep blocking Podman operations outside the global registry lock.

**Non-Goals:**
- Change idle eligibility rules, restart readiness criteria, or public API responses.
- Serialize lifecycle operations for different crews.

## Decisions

- Use per-crew transition coordination shared by the idle reaper and wake path. Re-check activity and the in-flight state after acquiring coordination, then keep it through the Podman state transition and registry reconciliation. This prevents a successful wake from being followed by a delayed idle stop while avoiding a global lock around Podman calls.
- Move restart-leader cleanup and outcome publication to cover the entire leader path, starting immediately after election. Publish the outcome before setting the event, preserving the existing waiter contract and generation checks.
- Add deterministic concurrency tests with barriers around the stop/start calls, and inject failures into the initial probe and early stop. Timing-based sleeps would make these races unreliable to reproduce.

## Risks / Trade-offs

- [Risk] A per-crew transition guard can delay a wake while a Podman stop is slow → Keep the guard scoped to one crew, preserve the existing 150-second waiter timeout, and do not hold the registry lock during the stop.
- [Risk] A guard acquired in one path but not released on every exception can deadlock that crew → Use context-managed acquisition and test all early exit paths.

# Design

## Context

Startup reconciliation iterates over every registry entry and performs a full restart cycle for stopped containers before the transport serves health requests. Restarted crews remain running, so memory use accumulates. The normal recovery path already applies config, refreshes cookies, checks capacity, serializes same-crew restarts and reconciles schedules.

## Goals / Non-Goals

**Goals:** Keep startup bounded by registry and Podman state inspection; retain demand-driven work and durable schedules.

**Non-Goals:** Replace crew containers with new images, alter workspace deletion, or change documented missed-job delivery semantics.

## Decisions

1. Reconcile existence and actual state only: mark stopped containers stopped without starting them; retain guarded removal for confirmed missing containers and do not delete on transient errors. Avoid waiting for gateways of stopped crews before readiness. Preserve running-container handling and dashboard registration.
2. Route explicit operations and due monitor work through `_ensure_crew_running`, including patching, gateway readiness, cookie refresh, schedule reconciliation, locks and capacity checks. Keep disabled and future jobs dormant. The transport can wake a stopped crew only for schedules recorded in its registry: a cron created solely inside a gateway is invisible while that gateway is stopped. Document that limitation and recommend Ghostship-managed schedules for automatic wakeup; when a crew next wakes, reconcile gateway state without treating stale cache entries as guaranteed current. Preserve existing best-effort missed-job semantics without promising exactly-once execution.
3. Multiple due schedules may trigger starts as the monitors run, potentially before HTTP readiness. Make cross-crew active-limit and memory admission atomic with reservations held across the start transition, release reservations on success, error and cancellation, and reconcile reservations with actual Podman state. Same-crew waiters share a single start. Do not hold the registry lock over gateway waits; test overlapping distinct-crew starts and failure cleanup.
4. Preserve existing images and persistent volumes. Document that new image adoption requires crew recreation or a separate upgrade mechanism, not automatic container replacement.
5. Before writing a stopped status observed during reconciliation, verify the record and container state are still current or coordinate with the same per-crew recovery generation. An in-flight or completed wake must not be overwritten by a stale startup snapshot. Preserve timestamp-guarded deletion and avoid blocking unrelated crews.

## Risks / Trade-offs

- Jobs may wake several crews shortly after startup → test due scheduling and admission under memory pressure; report failures using existing semantics.
- Gateway-only cron entries cannot trigger a stopped crew → document the boundary and exercise discovery on an explicit wake.
- Existing code relies on eager enrollment or route restoration → check first wake, dashboard access, Captain and dispatch end to end.

## Migration Plan

No registry migration is expected. Deploy the new transport under the normal approved process; existing stopped crews remain stopped and running crews retain their state. Rollback restores eager reconciliation and may again increase memory pressure.

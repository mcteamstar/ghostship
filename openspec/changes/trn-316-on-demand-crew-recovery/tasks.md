# Tasks

## 1. Startup reconciliation

- [ ] 1.1 Change reconciliation to retain stopped containers without starting them, correct stale status, retain running crews and preserve guarded cleanup for confirmed absent containers; verify mixed-state, transient-error and idempotency tests, including a concurrent wake between observation and write.
- [ ] 1.2 Preserve route allocation, registry metadata, workspace volumes and prompt transport readiness without gateway waits for stopped crews; verify startup tests with multiple stopped crews and a running crew.

## 2. Demand-driven recovery and schedules

- [ ] 2.1 Verify first dispatch, dashboard access and other existing wake paths still apply configuration, refresh credentials, enroll agents and reconcile schedules; add regression tests for stopped crews after restart.
- [ ] 2.2 Verify future and disabled tracked schedules remain dormant, while due tracked schedules and Captain check-ins wake the correct crew using existing delivery semantics; test gateway-only cron discovery on wake, stale registry state, reseeding, failures and restart boundaries.
- [ ] 2.3 Implement atomic cross-crew capacity admission or reservations across overlapping starts, with cleanup on failures and cancellation; verify same-crew coordination, simultaneous distinct-crew starts, active-crew and memory limits without holding registry locks over gateway waits.

## 3. Documentation and integration

- [ ] 3.1 Update operator documentation to explain on-demand recovery, tracked schedule wakeups, gateway-only schedule limitations and the fact that existing containers retain their image; verify examples against implementation.
- [ ] 3.2 Run affected unit and integration tests and an isolated restart exercise with multiple stopped crews, confirming health readiness, no eager wakeup and subsequent on-demand recovery; record results and any deployment requirements.

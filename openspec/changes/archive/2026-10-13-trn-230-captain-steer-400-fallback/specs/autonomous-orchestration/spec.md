# Spec Delta

## ADDED Requirements

### Requirement: Captain monitor recovers from 400 on /continue by re-dispatching
When the captain monitor calls `_steer_captain_checkin` and the `/api/spawn/{task_id}/continue` endpoint returns `400 Bad Request` (indicating the session is no longer continuable — i.e. the prior Raven task has finished), the transport SHALL treat this the same as a `404 conversation_gone` response: fall back to `_dispatch_captain_checkin` to start a fresh Raven check-in rather than propagating an unresponsive-crew error. The `current_task_id` SHALL be cleared from the registry before the fallback dispatch so that subsequent monitor ticks do not retry the dead task.

The `400 Bad Request` response on `/continue` SHALL NOT be routed to the stale-cookie recovery path (`_phase1_stale_cookie`) — a dead session cannot be recovered by refreshing the cookie.

#### Scenario: Captain monitor recovers after Raven completes
- **WHEN** the captain monitor ticks and the registered `current_task_id` points to a completed Raven task whose gateway session has ended (gateway returns 400 on `/continue`)
- **THEN** the transport falls back to dispatching a fresh Raven check-in via `_dispatch_captain_checkin`, clears `current_task_id` in the registry, and logs an info message — it does NOT log a CrewUnresponsiveError or stall on subsequent ticks

#### Scenario: 400 on /continue is not treated as stale cookie
- **WHEN** `/api/spawn/{task_id}/continue` returns `400 Bad Request`
- **THEN** `_crew_api_with_recovery` re-raises the error immediately without entering the stale-cookie retry path

#### Scenario: 400 on other paths still uses stale-cookie recovery
- **WHEN** a non-`/continue` path (e.g. `/api/spawn` dispatch) returns `400 Bad Request`
- **THEN** `_crew_api_with_recovery` continues to route through the existing phase-1 stale-cookie recovery path unchanged

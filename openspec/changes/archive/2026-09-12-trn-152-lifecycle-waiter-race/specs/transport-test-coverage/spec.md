# transport-test-coverage — Delta Spec (trn-152-lifecycle-waiter-race)

Updates to the `transport-test-coverage` capability.

## ADDED Requirements

### Requirement: _crew_api_with_recovery test coverage

The test suite SHALL exercise `_crew_api_with_recovery` and its three phase helpers using mocked HTTP responses, verifying retry behaviour and error propagation.

#### Scenario: Phase 0 — transient 503 is retried
- **WHEN** `_crew_api_with_recovery` receives a 503 from the first call
- **THEN** `_phase0_transient_503` retries the call and returns the second response

#### Scenario: Phase 1 — stale cookie triggers refresh
- **WHEN** `_crew_api_with_recovery` receives a 401 indicating a stale cookie
- **THEN** `_phase1_stale_cookie` refreshes the cookie and retries the call

#### Scenario: Phase 2 — dead gateway triggers container restart
- **WHEN** `_crew_api_with_recovery` cannot reach the crew gateway
- **THEN** `_phase2_dead_gateway` restarts the container, waits for readiness, and retries

#### Scenario: _ensure_crew_running leader failure propagates to waiters
- **WHEN** the leader coroutine in `_ensure_crew_running` raises during restart
- **THEN** waiters that were blocked on the same Event receive the same exception rather than proceeding with stale registry status

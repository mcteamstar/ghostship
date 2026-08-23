## ADDED Requirements

### Requirement: CSRF/cookie auto-recovery on stale credentials
The transport SHALL detect stale session credentials when `_crew_api` receives a 400, 401, or 403 response from a running container, transparently re-mint the session cookie via `container_exec` (`kirocrew token --ttl ...`), update the registry, and retry the original request exactly once — without user intervention. If the re-mint fails, the transport SHALL escalate to a full container restart via `_ensure_crew_running`.

#### Scenario: Stale cookie triggers transparent refresh
- **WHEN** `_crew_api` sends a request to a running crew container and receives a 400, 401, or 403 HTTP response
- **THEN** the transport mints a new session cookie, updates the registry, and retries the original request with the fresh cookie

#### Scenario: Successful retry after cookie refresh
- **WHEN** the retried request with the fresh cookie succeeds
- **THEN** the original caller receives the successful response as if the stale-cookie episode never happened

#### Scenario: Cookie re-mint fails
- **WHEN** the transport detects a stale credential and the `_mint_cookie` call returns no valid cookie
- **THEN** the transport escalates to a full container restart via `_ensure_crew_running` before retrying

#### Scenario: Retry limit prevents infinite loops
- **WHEN** a request has already been retried once after credential refresh (or once after container restart)
- **THEN** the transport does not attempt further retries and surfaces the error to the caller

### Requirement: Gateway liveness probe
The transport SHALL distinguish between "container stopped" and "container running but gateway unresponsive" by performing a lightweight HTTP probe against the gateway URL before treating a running container as healthy. If the probe fails on a running container, the transport SHALL treat it as a gateway crash and execute the recovery path (container restart, gateway wait, cookie refresh).

#### Scenario: Probe succeeds on a running container
- **WHEN** `_ensure_crew_running` finds the container running and the gateway liveness probe succeeds
- **THEN** the container is treated as healthy with no further action

#### Scenario: Probe fails on a running container
- **WHEN** `_ensure_crew_running` finds the container running but the gateway liveness probe fails (connection refused, timeout, or non-2xx on the probe endpoint)
- **THEN** the transport restarts the container, waits for the gateway, refreshes the session cookie, and updates the registry — the same recovery path as a stopped container

#### Scenario: Probe timeout is bounded
- **WHEN** the gateway liveness probe is issued
- **THEN** it SHALL complete (succeed or fail) within 5 seconds, so a hung gateway does not block the caller indefinitely

### Requirement: Retry with backoff on transient failures
The transport SHALL wrap `_crew_api` calls in a retry layer that attempts recovery at most once per failure class: on 400/401/403 from a running container, attempt cookie refresh then retry; on connection error from a running container, attempt gateway restart then retry. After two consecutive failures (refresh + retry both failed, or restart + retry both failed), the transport SHALL stop retrying and surface a clear error.

#### Scenario: Connection error triggers restart-then-retry
- **WHEN** `_crew_api` raises a connection error and the container is running
- **THEN** the transport restarts the gateway via `_ensure_crew_running` and retries the request once

#### Scenario: Two consecutive failures surface an error
- **WHEN** the retry after recovery also fails (second 400/401/403, or second connection error)
- **THEN** the transport does not attempt further recovery and raises a descriptive error to the caller

### Requirement: User-facing error messages on recovery failure
The transport SHALL return a human-readable error message when all recovery attempts are exhausted, stating the crew identifier, what was attempted, and a suggested next action — not a raw HTTP status code or Python traceback.

#### Scenario: Recovery exhausted error format
- **WHEN** a `_crew_api` call fails after all retry/recovery attempts
- **THEN** the error message includes the crew identifier, states that the transport attempted recovery (cookie refresh and/or restart), and suggests the caller retry momentarily or check the crew's status

#### Scenario: Error does not leak internal details
- **WHEN** a recovery-failure error is surfaced to the caller
- **THEN** the message does not include raw HTTP response bodies, Python stack traces, or internal container names beyond the crew_id

### Requirement: Gateway health field in crews() output
The `crews()` tool SHALL include a `gateway_healthy: bool` field in each crew entry, reflecting whether the gateway liveness probe succeeded at the time of the call. This allows operators to see at a glance which crews have a responsive gateway versus a running-but-broken one.

#### Scenario: Healthy gateway
- **WHEN** `crews()` is called and a crew's container is running and its gateway responds to the liveness probe
- **THEN** that crew's entry includes `gateway_healthy: true`

#### Scenario: Unresponsive gateway
- **WHEN** `crews()` is called and a crew's container is running but its gateway does not respond to the liveness probe
- **THEN** that crew's entry includes `gateway_healthy: false`

#### Scenario: Stopped container
- **WHEN** `crews()` is called and a crew's container is stopped
- **THEN** that crew's entry includes `gateway_healthy: false` (no gateway to probe)

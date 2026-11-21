# transport/crew-gateway Specification

## Purpose

Defines crew gateway authentication, operation recovery, and caller-facing failure contracts.

## Requirements

### Requirement: Bounded gateway session-token lifetime
The system SHALL mint gateway session tokens used to establish crew session cookies with a configurable lifetime, defaulting to 24 hours rather than one year, and SHALL use that setting consistently during initial setup, stopped-crew recovery, and transport-startup reconciliation.

#### Scenario: Default gateway token lifetime
- **WHEN** a crew is set up or its session is refreshed without an explicit gateway token lifetime configuration
- **THEN** the transport requests a gateway token with a 24-hour lifetime before exchanging it for the stored session cookie

#### Scenario: Configured gateway token lifetime
- **WHEN** the transport is given a valid gateway token lifetime configuration
- **THEN** initial setup and every later cookie refresh use that configured lifetime

#### Scenario: File-transfer URL lifetime remains independent
- **WHEN** a gateway session token lifetime is changed
- **THEN** the existing `GA_FILE_TTL_SECS` expiry for `evac` and `supply` URLs remains unchanged

### Requirement: CSRF/cookie auto-recovery on stale credentials

Transport SHALL refresh credentials and retry once when the gateway explicitly rejects a request for refreshable stale credentials before the operation executes. Plain HTTP status codes alone SHALL NOT establish a stale credential.

#### Scenario: Stale cookie triggers transparent refresh
- **WHEN** the gateway confirms the request was refused due to refreshable stale credentials
- **THEN** Transport mints a fresh cookie, updates the registry, and retries once

#### Scenario: Successful retry after cookie refresh
- **WHEN** the retried request succeeds
- **THEN** the caller receives its successful response

#### Scenario: Cookie re-mint fails
- **WHEN** confirmed stale credentials cannot be refreshed
- **THEN** Transport may restore the crew and retry only if the operation permits replay or rejection before execution is established

#### Scenario: Retry limit prevents infinite loops
- **WHEN** credential refresh or restoration has already been attempted for the request
- **THEN** further recovery follows the bounded operation policy and surfaces failure when exhausted

#### Scenario: Payload is refused
- **WHEN** a gateway rejects the request payload without identifying refreshable stale credentials
- **THEN** Transport reports the rejection without credential refresh or restart

### Requirement: Gateway liveness probe
The transport SHALL distinguish between "container stopped" and "container running but gateway unresponsive" by performing a lightweight HTTP probe against the gateway URL before treating a running container as healthy. If the probe fails on a running container, the transport SHALL treat it as a gateway crash and execute the recovery path.

#### Scenario: Probe succeeds on a running container
- **WHEN** `_ensure_crew_running` finds the container running and the gateway liveness probe succeeds
- **THEN** the container is treated as healthy with no further action

#### Scenario: Probe fails on a running container
- **WHEN** `_ensure_crew_running` finds the container running but the gateway liveness probe fails
- **THEN** the transport restarts the container, waits for the gateway, refreshes the session cookie, and updates the registry

#### Scenario: Probe timeout is bounded
- **WHEN** the gateway liveness probe is issued
- **THEN** it SHALL complete within 5 seconds so a hung gateway does not block the caller indefinitely

### Requirement: Retry with backoff on transient failures

Transport SHALL use a bounded retry policy per gateway operation. Reads may retry after recovery. Side-effecting operations SHALL retry only if the prior attempt is known to have been rejected before execution.

#### Scenario: Connection error triggers restart-then-retry
- **WHEN** a read encounters a connection error and the running container has an unresponsive gateway
- **THEN** Transport may restore the gateway and retry the read within its retry budget

#### Scenario: Two consecutive failures surface an error
- **WHEN** the recovery retry fails and the retry budget is exhausted
- **THEN** Transport surfaces a descriptive error

#### Scenario: Write response is lost
- **WHEN** Transport cannot tell whether the gateway accepted a side-effecting request
- **THEN** Transport reports unknown acceptance for reconciliation and does not replay the request

#### Scenario: Gateway accepted a task that later fails
- **WHEN** a continuation returns an accepted task ID and the task later fails
- **THEN** the task ID and terminal outcome remain available to the caller

### Requirement: /continue path detection uses endswith, not substring match

Transport SHALL identify continuation by the gateway operation or exact final path component. A path match alone SHALL NOT classify credentials or establish whether a write was accepted.

#### Scenario: /continue path is correctly identified
- **WHEN** the gateway returns HTTP 400 on an actual continuation route
- **THEN** Transport identifies the continuation and uses structured gateway evidence to classify the failure

#### Scenario: Non-/continue path containing "continue" is not misidentified
- **WHEN** the gateway returns HTTP 400 on a route that only contains the word continue in a different path component
- **THEN** Transport applies that route's operation policy and refreshes credentials only on a confirmed stale credential refusal

### Requirement: Cookie refresh is atomic under the registry lock

The transport SHALL update the in-memory crew entry's `cookie` field inside the
registry lock, atomically with the registry persistence call. No window SHALL exist
between the registry save and the in-memory update during which a concurrent reader
could observe a stale cookie value.

#### Scenario: Concurrent request sees fresh cookie after refresh
- **WHEN** `_refresh_cookie` completes for crew X
- **THEN** any concurrent request reading `crew["cookie"]` for crew X sees either
  the old cookie (before lock acquisition) or the new cookie (after release), never
  a state where the registry has the new cookie but the dict still has the old one

### Requirement: Gateway failures report actionable and redacted diagnostics

When recovery is exhausted, Transport SHALL report the crew, recovery attempted, and next action. If a gateway response is available, include its final HTTP status and sanitized detail. Before logging or returning gateway detail, redact credentials, collapse whitespace, and cap the detail at 500 characters. Omit stack traces, internal container names and internal endpoint paths. Diagnostic formatting does not determine retry eligibility.

#### Scenario: Recovery exhausted error format
- **WHEN** a `_crew_api` call fails after all retry/recovery attempts
- **THEN** the error message includes the crew identifier, states that the transport attempted recovery, and suggests the caller retry momentarily or check the crew's status

#### Scenario: Stale-cookie recovery failure surfaces actionable message
- **WHEN** an MCP tool call to a crew fails after the transport exhausted cookie-refresh and restart recovery
- **THEN** the MCP error response includes a message like "crew <crew_id> is unresponsive — the transport attempted recovery but the gateway did not come back. Try calling again in a moment or check crew status with crews()."

#### Scenario: Connection-error recovery failure surfaces actionable message
- **WHEN** an MCP tool call to a crew fails due to a connection error after the transport attempted a restart
- **THEN** the MCP error response includes a message identifying the crew, stating restart was attempted, and suggesting the caller retry or inspect the crew

#### Scenario: Unknown persona is reported, not just "unresponsive"
- **WHEN** a dispatch to a crew whose gateway answers `POST /api/spawn` with HTTP 400 and a body naming an unknown agent exhausts recovery
- **THEN** the error returned to the MCP caller includes `400` and the gateway's reason (for example that agent `ghost` was not found), alongside the existing recovery summary

#### Scenario: Long or credential-bearing bodies are bounded
- **WHEN** the gateway's final error body is longer than 500 characters or contains the crew's session cookie value
- **THEN** the caller receives at most 500 characters of it, with the cookie value replaced by a redaction marker

#### Scenario: Crew cookie is redacted from gateway error body
- **WHEN** a crew gateway returns an HTTP error response whose body contains the crew's session cookie value
- **THEN** the error text surfaced to the MCP caller does not contain the raw cookie value; it is replaced with `[redacted]`

#### Scenario: mc_token cookie is redacted from gateway error body
- **WHEN** a crew gateway returns an HTTP error response whose body contains a `mc_token_<port>=<value>` substring
- **THEN** the error text surfaced to the MCP caller replaces the value with `mc_token=[redacted]`

#### Scenario: Authorization Bearer value is redacted from gateway error body
- **WHEN** a crew gateway returns an HTTP error response whose body contains an `Authorization: Bearer <token>` substring
- **THEN** the error text surfaced to the MCP caller does not contain the raw token value; the Bearer value is replaced with `[redacted]`

#### Scenario: gs_session cookie value is redacted from gateway error body
- **WHEN** a crew gateway returns an HTTP error response whose body contains a `gs_session=<value>` cookie substring
- **THEN** the error text surfaced to the MCP caller does not contain the raw session token; it is replaced with `[redacted]`

#### Scenario: gs_csrf cookie value is redacted from gateway error body
- **WHEN** a crew gateway returns an HTTP error response whose body contains a `gs_csrf=<value>` cookie substring
- **THEN** the error text surfaced to the MCP caller does not contain the raw CSRF token; it is replaced with `[redacted]`

#### Scenario: Body is truncated to a bounded maximum
- **WHEN** a crew gateway returns an HTTP error response with a body longer than the configured maximum
- **THEN** the body is truncated to that maximum length before being surfaced to the caller, regardless of redaction

#### Scenario: Body with no sensitive material passes through (redacted only)
- **WHEN** a crew gateway returns an HTTP error response whose body contains no credential or session material
- **THEN** the error text surfaced to the caller is the (possibly truncated) raw body text with whitespace collapsed, unchanged by the redaction pass

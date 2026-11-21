## MODIFIED Requirements

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

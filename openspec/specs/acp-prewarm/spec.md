# ACP Prewarm Specification

## Purpose

Keeps ACP crew sessions warm in the background so later operations can start faster without exposing a separate client-facing prewarm operation.

## Requirements

### Requirement: Prewarm remains an internal capability

The transport SHALL keep `_prewarm_crew` as the canonical prewarm entry point and SHALL NOT expose prewarming as an MCP tool or REST route.

#### Scenario: Prewarm is not exposed as an MCP tool
- **WHEN** an MCP client lists available tools
- **THEN** no `prewarm` tool appears in the schema

#### Scenario: Prewarm exposed over REST with auth
- **WHEN** `POST /crews/{crew_id}/prewarm` is called
- **THEN** the transport returns 404; the route no longer exists

#### Scenario: Prewarm REST rejects missing or invalid auth
- **WHEN** `POST /crews/{crew_id}/prewarm` is called without a valid `GA_API_KEY`
- **THEN** the request reaches the generic 404 handler; no authentication check for this route is performed

### Requirement: Background prewarm warms crew sessions

Crew setup SHALL invoke `_prewarm_crew` automatically. Successful `supply` calls after presigned-URL issuance and `schedule` calls after new job creation SHALL start non-blocking background prewarms; failures SHALL be logged at WARNING without failing the caller.

#### Scenario: Prewarm a stopped crew
- **WHEN** `_prewarm_crew` is called for a registered crew whose container is stopped, and the memory and active-crew gates permit a start
- **THEN** the transport starts the container, waits for the gateway to become ready, causes the session process to be forked with a completed ACP handshake, and returns a status indicating the crew is now warm

#### Scenario: Prewarm returns without blocking on real work
- **WHEN** a background prewarm is triggered by `supply` or `schedule`
- **THEN** the calling tool returns before the prewarm completes, and no `dispatch` of real agent work is issued as part of the warm-up

#### Scenario: Prewarm is triggered implicitly by supply
- **WHEN** `supply` successfully issues a presigned URL for a crew
- **THEN** a background warm-up is started for that crew

#### Scenario: Prewarm is triggered implicitly by schedule
- **WHEN** `schedule` (action=create) successfully creates a new job for a crew
- **THEN** a background warm-up is started for that crew

#### Scenario: Prewarm background failure does not fail the caller
- **WHEN** the background warm-up triggered by `supply` or `schedule` raises an exception
- **THEN** the exception is logged at WARNING level and the response from `supply` or `schedule` is unaffected

#### Scenario: Crew setup invokes prewarm
- **WHEN** crew setup reaches its automatic warm-up step
- **THEN** the transport invokes the internal `_prewarm_crew` operation without requiring a client call

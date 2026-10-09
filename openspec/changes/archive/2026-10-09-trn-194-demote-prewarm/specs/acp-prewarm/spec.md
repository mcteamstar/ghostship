# Delta Spec: ACP Prewarm

## MODIFIED Requirements

### Requirement: Prewarm operation establishes a warm ACP session

The transport SHALL maintain prewarm as an internal capability only. The `prewarm` MCP tool and the `POST /crews/{crew_id}/prewarm` REST endpoint SHALL be removed. No MCP client SHALL see a `prewarm` tool in the schema. The internal `_prewarm_crew` function SHALL remain the canonical entry point; all prewarm functionality SHALL be invoked either automatically at crew setup or implicitly by other tools.

The prewarm operation SHALL be triggered implicitly as a background side-effect of `supply` (after issuing a presigned URL) and `schedule` (after creating a new job). These background warm-ups SHALL be non-blocking and non-fatal: any exception SHALL be logged at WARNING and SHALL NOT propagate to the calling tool.

#### Scenario: Prewarm a stopped crew
- **WHEN** `_prewarm_crew` is called for a registered crew whose container is stopped, and the memory and active-crew gates permit a start
- **THEN** the transport starts the container, waits for the gateway to become ready, causes the session process to be forked with a completed ACP handshake, and returns a status indicating the crew is now warm

#### Scenario: Prewarm returns without blocking on real work
- **WHEN** a background prewarm is triggered by `supply` or `schedule`
- **THEN** the calling tool returns before the prewarm completes, and no `dispatch` of real agent work is issued as part of the warm-up

#### Scenario: Prewarm is not exposed as an MCP tool
- **WHEN** an MCP client lists available tools
- **THEN** no `prewarm` tool appears in the schema

#### Scenario: Prewarm exposed over REST with auth
- **WHEN** `POST /crews/{crew_id}/prewarm` is called
- **THEN** the transport returns 404; the route no longer exists

#### Scenario: Prewarm REST rejects missing or invalid auth
- **WHEN** `POST /crews/{crew_id}/prewarm` is called without a valid `GA_API_KEY`
- **THEN** the request reaches the generic 404 handler; no authentication check for this route is performed

#### Scenario: Prewarm is triggered implicitly by supply
- **WHEN** `supply` successfully issues a presigned URL for a crew
- **THEN** a background warm-up is started for that crew

#### Scenario: Prewarm is triggered implicitly by schedule
- **WHEN** `schedule` (action=create) successfully creates a new job for a crew
- **THEN** a background warm-up is started for that crew

#### Scenario: Prewarm background failure does not fail the caller
- **WHEN** the background warm-up triggered by `supply` or `schedule` raises an exception
- **THEN** the exception is logged at WARNING level and the response from `supply` or `schedule` is unaffected

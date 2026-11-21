# crew-lifecycle/startup Specification

## Purpose

Defines crew readiness, warm-up, restart and startup coordination.

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

### Requirement: _ensure_crew_running checks registry entry after container_start
After `container_start` returns and before proceeding with post-start setup (cookie write, member enrollment, etc.), `_ensure_crew_running` SHALL verify that the crew's registry entry still exists. If the entry has been removed (e.g. by a concurrent `nuke()`), the function SHALL log an info message and return without error, treating the removal as an intentional teardown.

#### Scenario: Nuke during restart is handled gracefully
- **WHEN** `nuke()` removes a crew's registry entry while `_ensure_crew_running` is mid-restart
- **THEN** `_ensure_crew_running` detects the missing entry after `container_start`, skips post-start setup, and returns without error or spurious log noise

### Requirement: Restart applies required configuration before final gateway wait

The restart path SHALL start provisionally, apply the config patch (creating its directory if needed), stop and start again, then wait once for the final gateway; it SHALL NOT wait after the provisional start.

#### Scenario: Single gateway wait on wake
- **WHEN** a stopped crew container is woken through the normal stopped-container path
- **THEN** the container is started exactly twice, stopped once for the configuration bounce, and the gateway wait is performed exactly once after the final start; no gateway wait occurs between the provisional start and the exec patch

### Requirement: Concurrent crew wake uses one generation-stable restart cycle

Crew startup SHALL elect one leader per crew and register waiters under the same startup-state lock. The leader SHALL record the outcome before signaling waiters, including on early exits. Waiters SHALL allow up to 150 seconds and use only the outcome for their captured generation. Calls for different crews may proceed concurrently subject to shared admission limits.

#### Scenario: Concurrent callers share one crew restart cycle
- **WHEN** two or more callers wake a stopped crew concurrently
- **THEN** one leads the restart cycle and the others wait for its recorded result
- **AND** a successful waiter proceeds with the refreshed crew record without starting a second cycle

#### Scenario: Waiter does not time out during normal leader restart
- **WHEN** a leader restart takes up to 120 seconds to complete
- **THEN** waiters do not raise a timeout error before the leader signals completion

#### Scenario: Two waiters, leader fails — both see the failure

- **WHEN** two callers arrive after a leader has been elected for `crew_id`
- **AND** the leader's restart fails
- **THEN** both waiters read `success=False` from `_crew_restart_outcomes` and raise the stored exception
- This is the existing TRN-152 behavior; the generation counter SHALL NOT break it.

#### Scenario: Concurrent auto-start calls for different crews
- **WHEN** two callers invoke `_ensure_crew_running` concurrently for different `crew_id` values
- **THEN** both start sequences proceed concurrently without being serialised against each other

#### Scenario: Second caller sees already-running container
- **WHEN** a second caller acquires the per-crew lock after the first has already completed the start
- **THEN** the second caller finds the container already running and returns immediately without issuing another `container_start`

#### Scenario: Third concurrent caller does not corrupt prior waiters' outcome reads

- **GIVEN** a crew restart is in progress (leader A, waiter B)
- **WHEN** caller C arrives after the leader fires the event but before waiter B reads the outcome, and C is elected as the new leader for a fresh restart cycle
- **THEN** B detects the generation change and raises a RuntimeError rather than reading A's outcome as if it were valid for C's cycle
- **AND** B does not proceed against a crew whose state is indeterminate

#### Scenario: Leader restart fails — memory gate
- **WHEN** `_ensure_crew_running` is called for a stopped crew AND the memory gate blocks the restart
- **THEN** the leader sets a failure outcome on the Event AND waiters that were blocked on the same crew raise the same error (not proceed with a stale "running" status)

#### Scenario: Leader restart fails — gateway timeout
- **WHEN** `_ensure_crew_running` is called AND the restarted container's gateway does not become ready within the timeout
- **THEN** the leader records the failure on the Event AND waiters propagate the timeout error

#### Scenario: Initial container probe fails
- **WHEN** the elected restart leader's initial Podman running-state probe raises an exception
- **THEN** the leader records the failure and signals the shared Event
- **THEN** all waiters wake and receive the leader failure without waiting for the timeout

#### Scenario: Early stop before restart body fails
- **WHEN** the elected restart leader attempts to stop a running container whose gateway probe failed and `container_stop` raises
- **THEN** the leader records the failure and signals the shared Event
- **THEN** all waiters wake and receive the leader failure without waiting for the timeout

# Spec Delta

## MODIFIED Requirements

### Requirement: Concurrent crew wake uses one generation-stable restart cycle
Crew startup SHALL elect one leader per crew and register waiters under the same startup-state lock. The leader SHALL record the outcome before signaling waiters, including on early exits. Waiters SHALL allow up to 150 seconds and read the outcome for their captured generation; later generations SHALL NOT replace or invalidate an outcome while waiters from that generation may still read it. Calls for different crews may proceed concurrently subject to shared admission limits.

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
- **THEN** both waiters read `success=False` from the outcome for their captured generation and raise the stored exception
- **AND** a later generation does not replace the failure before either waiter reads it

#### Scenario: Concurrent auto-start calls for different crews
- **WHEN** two callers invoke `_ensure_crew_running` concurrently for different `crew_id` values
- **THEN** both start sequences proceed concurrently without being serialised against each other

#### Scenario: Second caller sees already-running container
- **WHEN** a second caller acquires the per-crew lock after the first has already completed the start
- **THEN** the second caller finds the container already running and returns immediately without issuing another `container_start`

#### Scenario: Third concurrent caller does not corrupt prior waiters' outcome reads
- **GIVEN** caller B is waiting on generation A and A has signaled its successful outcome
- **WHEN** caller C begins generation B before caller B reads generation A's outcome
- **THEN** caller B reads generation A's successful outcome and proceeds with the refreshed crew record
- **AND** caller B does not fail solely because generation B has begun

#### Scenario: Leader restart fails — memory gate
- **WHEN** `_ensure_crew_running` is called for a stopped crew AND the memory gate blocks the restart
- **THEN** the leader sets a failure outcome on the Event AND waiters that were blocked on the same crew raise the same error (not proceed with a stale "running" status)

#### Scenario: Leader restart fails — gateway timeout
- **WHEN** `_ensure_crew_running` is called AND the restarted container's gateway does not become ready within the timeout
- **THEN** the leader records the failure on the Event AND waiters propagate the timeout error

#### Scenario: Initial container probe fails
- **WHEN** the elected restart leader's initial Podman running-state probe raises an exception
- **THEN** the leader records the failure and signals the shared Event
- **AND** all waiters wake and receive the leader failure without waiting for the timeout

#### Scenario: Early stop before restart body fails
- **WHEN** the elected restart leader attempts to stop a running container whose gateway probe failed and `container_stop` raises
- **THEN** the leader records the failure and signals the shared Event
- **AND** all waiters wake and receive the leader failure without waiting for the timeout

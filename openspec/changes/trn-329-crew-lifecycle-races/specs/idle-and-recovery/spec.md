# Spec Delta

## MODIFIED Requirements

### Requirement: _ensure_crew_running waiter propagates leader failure

When the leader coroutine in `_ensure_crew_running` fails to restart a crew (memory gate exceeded, active-crew limit, gateway timeout, or any other exception), it SHALL record an explicit failure outcome on the shared Event before releasing it. Waiter coroutines that wake from that Event SHALL read the recorded outcome and raise the leader's error rather than inferring crew health from registry status. The leader SHALL also record an outcome and signal waiters when failure occurs during leader setup before the main restart body, including the initial container-running probe or an early container stop.

#### Scenario: Leader restart fails — memory gate
- **WHEN** `_ensure_crew_running` is called for a stopped crew AND the memory gate blocks the restart
- **THEN** the leader sets a failure outcome on the Event AND waiters that were blocked on the same crew raise the same error (not proceed with a stale "running" status)

#### Scenario: Leader restart fails — gateway timeout
- **WHEN** `_ensure_crew_running` is called AND the restarted container's gateway does not become ready within the timeout
- **THEN** the leader records the failure on the Event AND waiters propagate the timeout error

#### Scenario: Leader restart succeeds — waiters proceed normally
- **WHEN** `_ensure_crew_running` completes successfully
- **THEN** the leader records success on the Event AND waiters proceed to make their API call as before

#### Scenario: Initial container probe fails
- **WHEN** the elected restart leader's initial Podman running-state probe raises an exception
- **THEN** the leader records the failure and signals the shared Event
- **THEN** all waiters wake and receive the leader failure without waiting for the timeout

#### Scenario: Early stop before restart body fails
- **WHEN** the elected restart leader attempts to stop a running container whose gateway probe failed and `container_stop` raises
- **THEN** the leader records the failure and signals the shared Event
- **THEN** all waiters wake and receive the leader failure without waiting for the timeout

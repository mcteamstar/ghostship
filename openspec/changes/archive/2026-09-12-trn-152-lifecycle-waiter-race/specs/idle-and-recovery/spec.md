# idle-and-recovery — Delta Spec (trn-152-lifecycle-waiter-race)

Updates to the `idle-and-recovery` capability.

## MODIFIED Requirements

### Requirement: _ensure_crew_running waiter propagates leader failure

The existing `_ensure_crew_running` requirement is modified: when the leader coroutine fails to restart a crew (memory gate exceeded, active-crew limit, gateway timeout, or any other exception), it SHALL record an explicit failure outcome on the shared Event before releasing it. Waiter coroutines that wake from that Event SHALL read the recorded outcome and raise the leader's error rather than inferring crew health from registry status.

#### Scenario: Leader restart fails — memory gate
- **WHEN** `_ensure_crew_running` is called for a stopped crew AND the memory gate blocks the restart
- **THEN** the leader sets a failure outcome on the Event AND waiters that were blocked on the same crew raise the same error (not proceed with a stale "running" status)

#### Scenario: Leader restart fails — gateway timeout
- **WHEN** `_ensure_crew_running` is called AND the restarted container's gateway does not become ready within the timeout
- **THEN** the leader records the failure on the Event AND waiters propagate the timeout error

#### Scenario: Leader restart succeeds — waiters proceed normally
- **WHEN** `_ensure_crew_running` completes successfully
- **THEN** the leader records success on the Event AND waiters proceed to make their API call as before

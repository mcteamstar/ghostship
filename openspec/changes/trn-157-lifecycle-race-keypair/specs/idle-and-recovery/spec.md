# Idle and Recovery — Delta Spec (TRN-157)

## Requirement: Concurrent restart waiters observe generation-stable outcomes

This delta amends the "Transparent restart on next use" requirement's concurrent-callers scenario to add the generation-stable guarantee.

The existing requirement states: "A second call for the same crew waits for the in-progress restart to finish and then uses the refreshed crew record, rather than triggering a second concurrent restart."

This is extended: a waiter SHALL also verify that the restart cycle it waited on is the same cycle it wakes into. If a new leader has begun a fresh restart cycle before the waiter reads `_crew_restart_outcomes`, the waiter SHALL NOT silently read stale state from the prior cycle. Instead the waiter SHALL raise a RuntimeError indicating that the restart cycle changed during its wait.

#### Scenario: Third concurrent caller does not corrupt prior waiters' outcome reads

- **GIVEN** a crew restart is in progress (leader A, waiter B)
- **WHEN** caller C arrives after the leader fires the event but before waiter B reads the outcome, and C is elected as the new leader for a fresh restart cycle
- **THEN** B detects the generation change and raises a RuntimeError rather than reading A's outcome as if it were valid for C's cycle
- **AND** B does not proceed against a crew whose state is indeterminate

#### Scenario: Generation stable — normal two-caller restart is unaffected

- **WHEN** exactly a leader and one waiter complete a restart cycle without any third caller
- **THEN** the generation counter does not change between the waiter's capture and its post-wait read, and the waiter proceeds normally using the leader's outcome

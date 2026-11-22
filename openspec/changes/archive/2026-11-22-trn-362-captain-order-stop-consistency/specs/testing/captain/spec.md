# Spec Delta

## ADDED Requirements

### Requirement: Captain stop and check-in synchronization has regression coverage
Captain tests SHALL exercise stop racing a check-in with synchronization controls rather than timing sleeps.

#### Scenario: Stop waits for an accepted in-flight check-in
- **WHEN** a check-in is paused at a controlled dispatch boundary and stop is invoked
- **THEN** the test verifies stop does not return until the in-flight check-in completes and the schedule is disabled

#### Scenario: No dispatch begins after stop returns
- **WHEN** stop completes before a scheduled check-in acquires the per-crew transition lock
- **THEN** the test verifies the check-in observes the disabled schedule and makes no Raven dispatch call

### Requirement: Captain order persistence failures have regression coverage
Captain order tests SHALL inject failures at schedule and mailbox persistence boundaries and verify returned status and persisted schedule state.

#### Scenario: Schedule persistence failure does not write mailbox instruction
- **WHEN** persisting the schedule transition raises an exception
- **THEN** the order call returns an error and the mailbox append helper is not called

#### Scenario: Mailbox failure leaves schedule disabled
- **WHEN** provisional schedule persistence succeeds and appending the standing instruction raises an exception
- **THEN** the order call returns an error and the schedule is disabled

#### Scenario: Final activation failure does not report ordered
- **WHEN** the instruction append succeeds but persisting the enabled schedule fails
- **THEN** the order call returns an error and does not report `status: ordered`

#### Scenario: Successful order aligns schedule and mailbox
- **WHEN** schedule persistence and instruction delivery both succeed
- **THEN** the schedule is enabled and the order call reports `status: ordered`

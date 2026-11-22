# Spec Delta

## ADDED Requirements

### Requirement: Captain stop serializes with scheduled check-ins
Captain stop SHALL serialize with per-crew check-in dispatch. When stop returns, no new scheduled check-in dispatch SHALL begin; an already-running check-in may finish before stop returns and SHALL NOT be cancelled.

#### Scenario: Stop waits for an in-flight check-in
- **GIVEN** a scheduled check-in has begun and holds the per-crew transition lock
- **WHEN** `captain(action="stop")` is called
- **THEN** stop waits for that check-in to finish before disabling the schedule and returning

#### Scenario: Check-in starting after stop observes the disabled schedule
- **GIVEN** `captain(action="stop")` has returned successfully
- **WHEN** a scheduled check-in attempts to acquire the per-crew transition lock
- **THEN** it observes the disabled schedule and does not dispatch Raven

### Requirement: Captain order reports success only after consistent persistence
Captain order SHALL report `status: ordered` only after its standing instruction is written and its schedule is persisted enabled. If a persistence step fails, the call SHALL return an error and SHALL NOT leave a schedule enabled without the corresponding instruction.

#### Scenario: Schedule persistence fails before instruction delivery
- **WHEN** Captain cannot persist the schedule transition before writing the standing instruction
- **THEN** the order call returns an error and does not append the instruction to the mailbox

#### Scenario: Instruction delivery fails after a provisional schedule write
- **WHEN** the provisional schedule write succeeds but writing the standing instruction fails
- **THEN** the order call returns an error and leaves the schedule disabled until a later order succeeds

#### Scenario: Final schedule activation fails after instruction delivery
- **WHEN** the standing instruction is written but Captain cannot persist the schedule as enabled
- **THEN** the order call returns an error and the schedule remains disabled

#### Scenario: Schedule and instruction are both persisted
- **WHEN** Captain persists the schedule and writes the standing instruction successfully
- **THEN** the schedule is enabled and the call returns `status: ordered`

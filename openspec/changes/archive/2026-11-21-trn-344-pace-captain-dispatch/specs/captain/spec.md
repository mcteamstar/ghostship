## ADDED Requirements

### Requirement: Captain paces multiple task starts in a check-in

Captain SHALL default to one task start per check-in. It SHALL start multiple independent tasks only when the standing order authorizes them, admit them sequentially, and reconcile each task identity, intent, and returned ID before the next start. A memory-pressure deferral or uncertain admission SHALL stop further starts for the check-in, with pending work reconciled before a later retry. Admitted tasks can continue in parallel.

#### Scenario: One task is eligible
- **WHEN** an order needs one next task
- **THEN** Captain dispatches that task using the normal intent protocol

#### Scenario: Several tasks are eligible
- **WHEN** an order explicitly authorizes several independent work items
- **THEN** Captain starts each authorized task sequentially and records its confirmed task ID before starting the next
- **AND** earlier admitted tasks can continue in parallel with later starts

#### Scenario: Memory pressure defers a dispatch
- **WHEN** admission defers a start due to memory pressure
- **THEN** Captain stops starting tasks for that check-in and leaves unconfirmed work pending
- **AND** later check-ins reconcile prior intents and task IDs before retrying pending work

#### Scenario: Admission outcome is uncertain
- **WHEN** Captain cannot confirm whether a task start was accepted
- **THEN** Captain stops further starts for that check-in and reconciles the intent and task ID before retrying on a later check-in

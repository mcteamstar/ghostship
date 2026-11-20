## ADDED Requirements

### Requirement: Captain can pace multiple dispatches in a check-in

Captain SHALL prefer one dispatch at a time. When an order calls for multiple eligible tasks, Captain MAY start them in one check-in, pacing starts and tracking admission per task. Memory deferral SHALL stop further starts that cycle and leave pending work for later reconciliation.

#### Scenario: One task is eligible
- **WHEN** an order needs one next task
- **THEN** Captain dispatches that task using the normal intent protocol

#### Scenario: Several tasks are eligible
- **WHEN** an order calls for several independent tasks
- **THEN** Captain may pace several starts in the current check-in and record each confirmed task ID
- **AND** previously started tasks may continue in parallel

#### Scenario: Memory pressure defers a dispatch
- **WHEN** admission defers a start due to memory pressure
- **THEN** Captain stops starting tasks for that cycle and leaves unconfirmed work pending
- **AND** later check-ins reconcile prior admissions before retrying pending work

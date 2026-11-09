# Spec Delta

## MODIFIED Requirements

### Requirement: Registry reconciliation on startup

The system SHALL reconcile the crew registry against actual Podman state on transport startup without starting stopped crew containers. It SHALL preserve their workspaces, schedules, dashboard allocations and registry records, and SHALL mark existing stopped containers stopped. It SHALL retain the existing guarded handling of containers confirmed absent and tolerate transient Podman errors without deleting records.

#### Scenario: Container no longer exists
- **WHEN** transport starts and a registered crew's container is confirmed absent from Podman
- **THEN** the system removes that crew from the registry under the existing guarded deletion rules

#### Scenario: Container exists but stopped
- **WHEN** transport starts and a registered crew's container exists but is not running
- **THEN** it remains stopped and registered without a gateway readiness wait or cookie mint

#### Scenario: Container is already running
- **WHEN** transport starts and a registered crew's container is running
- **THEN** it is reconciled without an unnecessary restart

#### Scenario: Podman state is unavailable
- **WHEN** an existence or running-state check fails transiently
- **THEN** the affected crew record is retained and the error is logged

#### Scenario: A crew wakes while reconciliation is in progress
- **WHEN** reconciliation observes a stopped crew and a concurrent operation starts it before the status write
- **THEN** the stale observation does not overwrite the newer running state

## ADDED Requirements

### Requirement: Due work wakes stopped crews after startup

The system SHALL preserve Ghostship-tracked schedules and Captain state across restart. Due work SHALL use guarded on-demand recovery when monitors run; future or disabled work SHALL NOT wake a crew before it is due. Existing schedule execution semantics SHALL continue to apply. A schedule present only in a stopped gateway is not discoverable until that crew wakes, and this limitation SHALL be documented.

#### Scenario: Enabled work is due
- **WHEN** an enabled schedule or Captain check-in becomes due for a stopped crew
- **THEN** the monitor attempts guarded crew recovery and processes the due work under existing scheduling semantics

#### Scenario: Work is not due
- **WHEN** a stopped crew has only future or disabled scheduled work
- **THEN** the monitor leaves the crew stopped until due work or an explicit operation requires it

#### Scenario: Several crews have due work
- **WHEN** several stopped crews have work due together
- **THEN** cross-crew admission atomically reserves capacity so simultaneous starts cannot independently consume the same available capacity, and per-crew restart coordination remains effective

#### Scenario: A start fails after reserving capacity
- **WHEN** a start fails or is cancelled after admission
- **THEN** its reservation is released and later eligible starts can proceed

#### Scenario: Gateway-only schedule on stopped crew
- **WHEN** a schedule exists only in a stopped crew gateway and is absent from the transport registry
- **THEN** it cannot trigger a wake until the crew is started for another reason, and the documented limitation applies

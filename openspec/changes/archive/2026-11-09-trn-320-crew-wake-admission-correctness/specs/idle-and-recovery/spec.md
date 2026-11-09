# Spec Delta

## MODIFIED Requirements

### Requirement: Due work wakes stopped crews after startup

The system SHALL preserve Ghostship-tracked schedules and Captain state across restart. Due work SHALL use guarded on-demand recovery when monitors run; future or disabled work SHALL NOT wake a crew before it is due. Existing schedule execution semantics SHALL continue to apply. A schedule present only in a stopped gateway is not discoverable until that crew wakes, and this limitation SHALL be documented. Memory admission SHALL account for starts that have been admitted but whose gateways are not yet ready. A wake that fails after its container was started SHALL leave that container stopped.

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

#### Scenario: In-flight start counts against free memory
- **WHEN** one crew has been admitted and started but its gateway is not yet ready, and a second crew requests a start while live free memory minus the in-flight estimate is below the configured floor
- **THEN** the second start waits or is refused for memory rather than being admitted on the live reading alone

#### Scenario: Memory wait does not block unrelated starts indefinitely
- **WHEN** one start is waiting for memory to recover
- **THEN** other crews' admission decisions are not held behind that wait for its full timeout

#### Scenario: Wake fails after the container started
- **WHEN** the configuration patch, gateway wait or cookie mint fails after the container was started during a wake
- **THEN** the container is stopped, its reservation is released, the registry records it stopped, and the caller receives the failure

#### Scenario: Gateway ready but cookie mint fails
- **WHEN** the gateway becomes ready during a wake but a fresh session cookie cannot be minted
- **THEN** the wake is reported as failed, the container is stopped, and waiters receive the same failure rather than a generic stopped-status error

# Spec Delta

## MODIFIED Requirements

### Requirement: OAuth login persistence failures are visible

The system SHALL report OAuth login success only after the selected profile's credential has been durably stored. If persistence fails, the system SHALL report failure and retain enough pending state to retry or explicitly recover, without leaking credentials or claiming completion. Once the credential is durably stored, a failure to propagate it to any running crew SHALL NOT change the login outcome, SHALL NOT keep the pending flow open for retry, and SHALL be reported per crew.

#### Scenario: Profile write fails
- **WHEN** the selected profile credential cannot be saved after OAuth completes
- **THEN** login reports an error rather than success and does not replace another profile's credential

#### Scenario: Retry after transient failure
- **WHEN** the profile write succeeds on a subsequent retry of the same valid pending flow
- **THEN** login reports success and the credential belongs only to the selected profile

#### Scenario: Propagation to a running crew fails after storage
- **WHEN** the credential is stored and injecting it into one running crew of the same backend and profile fails
- **THEN** login reports success, the failing crew is identified in the result or logs, other matching crews still receive the credential, and no further retry of the login flow occurs

## ADDED Requirements

### Requirement: Running crews keep their launch-time credentials

A running crew SHALL continue to serve tool calls and file transfers with the credential it was started with, regardless of later changes to the stored credential for its backend and profile. Static credential validation SHALL apply only when a stopped crew is being started.

#### Scenario: Static credential rotated while a crew runs
- **WHEN** an operator rotates the static credential for a profile while a crew using that profile is running
- **THEN** dispatch, pickup, steer, schedule, captain and file transfers against that crew continue to succeed without validation errors

#### Scenario: Evac after rotation
- **WHEN** an operator requests an evac from a running crew after its profile's static credential has rotated
- **THEN** the evac succeeds so the workspace can be extracted before any relaunch

#### Scenario: Stopped crew wakes after rotation
- **WHEN** a stopped crew is woken after its profile's static credential has changed in a way the container cannot adopt
- **THEN** the wake fails with an error that names the crew and profile and advises recreating the crew, and the crew is left stopped

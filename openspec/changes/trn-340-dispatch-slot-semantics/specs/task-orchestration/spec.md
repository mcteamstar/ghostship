# Spec Delta

## ADDED Requirements

### Requirement: Task dispatch and member-slot routing

The system SHALL dispatch a task to a named persona in a specified crew as a dedicated retained run and return a task ID. With slot=None, enrolled personas use their pre-created member DM slot and unenrolled personas run headless. slot=False forces headless dispatch. Arbitrary slot names and slot=True SHALL be rejected.

#### Scenario: Dispatch to an existing crew
- **WHEN** dispatch is called with a task, an agent, and an existing crew_id
- **THEN** the system ensures the crew is running, sends a dedicated-run request to /api/spawn, and returns a task ID, dispatched status, creation timestamp, and resolved slot

#### Scenario: Dispatch without crew_id when crews exist
- **WHEN** dispatch is called without crew_id and one or more crews are registered
- **THEN** the system returns an error listing live crew IDs instead of guessing

#### Scenario: Dispatch when no crews exist
- **WHEN** dispatch is called without crew_id and no crews are registered
- **THEN** the system returns an error instructing the caller to launch a crew first

#### Scenario: Enrolled persona uses its member slot by default
- **WHEN** dispatch is called without slot for an enrolled persona
- **THEN** /api/spawn uses parent_session dashboard:member-<slug> and the response identifies that member slot

#### Scenario: Unenrolled persona is headless by default
- **WHEN** dispatch is called without slot for an unenrolled persona
- **THEN** /api/spawn has no parent_session and the response has slot null

#### Scenario: Explicit false forces headless dispatch
- **WHEN** dispatch is called with slot=False for an enrolled persona
- **THEN** /api/spawn has no parent_session and the response has slot null

#### Scenario: Legacy bridge slot is rejected
- **WHEN** dispatch is called with slot=bridge
- **THEN** the request is rejected and no bridge session is created

#### Scenario: Legacy per-task slot is rejected
- **WHEN** dispatch is called with slot=True
- **THEN** the request is rejected and no unique dashboard session is created

#### Scenario: Legacy named slot is rejected
- **WHEN** dispatch is called with a string slot name
- **THEN** the request is rejected and no named dashboard session is created

#### Scenario: Repeated arbitrary slot names are rejected
- **WHEN** two dispatch calls use the same arbitrary string slot name
- **THEN** both requests are rejected and neither task is dispatched

#### Scenario: Dashboard allocation does not choose a bridge slot
- **WHEN** a crew has a dashboard port and an enrolled persona is dispatched without a slot argument
- **THEN** the task uses the persona's member DM slot, not a shared bridge slot

#### Scenario: No dashboard port does not change enrollment-based routing
- **WHEN** a crew has no dashboard port and an enrolled persona is dispatched without a slot argument
- **THEN** the task uses its pre-created member DM slot

## REMOVED Requirements

### Requirement: Task dispatch

**Reason**: Its bridge, arbitrary slot, and dashboard-port-derived defaults no longer match the dispatch tool contract.

**Migration**: Omit slot to use enrollment-based member-slot or headless resolution; pass slot=False to force headless dispatch. Do not use slot=True or string-valued slots.

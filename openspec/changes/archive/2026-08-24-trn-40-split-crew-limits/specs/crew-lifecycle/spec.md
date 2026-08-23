## MODIFIED Requirements

### Requirement: Crew creation via launch

The `launch` tool SHALL refuse to create a new crew when the number of
registered crews (running + stopped) is at or above `GA_MAX_CREWS` (default:
20). The error message SHALL distinguish between the total-registered limit and
the active-running limit.

#### Scenario: First launch for a new crew_id

- **WHEN** `launch` is called with a `crew_id` that has no existing registry
  entry and the registered crew count is below `GA_MAX_CREWS`
- **THEN** a new crew container and volumes are created and the crew is
  registered as "running"

#### Scenario: Max registered crews reached

- **WHEN** `launch` is called while the number of registered crews is already
  at or above `GA_MAX_CREWS`
- **THEN** `launch` returns an error indicating the registered crew limit has
  been reached and instructing the operator to nuke a crew first

## ADDED Requirements

### Requirement: Active crew limit enforced before restart

The transport SHALL enforce a separate limit on simultaneously running crew
containers via `GA_MAX_ACTIVE_CREWS` (default: 3). Before starting a stopped
crew container, `_ensure_crew_running` SHALL count the number of currently
running containers in the registry and refuse to start if the count is at or
above `GA_MAX_ACTIVE_CREWS`.

This limit protects host memory independently of the registered-crew count: an
operator can keep many idle crews registered while preventing too many from
running simultaneously.

#### Scenario: Active limit not reached

- **WHEN** `_ensure_crew_running` is called for a stopped crew and fewer than
  `GA_MAX_ACTIVE_CREWS` crew containers are currently running
- **THEN** the crew container is started normally

#### Scenario: Active limit reached

- **WHEN** `_ensure_crew_running` is called for a stopped crew and
  `GA_MAX_ACTIVE_CREWS` crew containers are already running
- **THEN** `_ensure_crew_running` raises `CrewUnresponsiveError` (or equivalent)
  with a clear message indicating the active crew limit and instructing the
  operator to wait for a running crew to idle out or nuke one

#### Scenario: Already-running crew is unaffected

- **WHEN** `_ensure_crew_running` is called for a crew that is already running
- **THEN** the active limit check is skipped — the crew is not counted a
  second time

#### Scenario: GA_MAX_ACTIVE_CREWS=0 disables the limit

- **WHEN** `GA_MAX_ACTIVE_CREWS` is set to `0`
- **THEN** the active limit check is skipped entirely — no cap on running crews

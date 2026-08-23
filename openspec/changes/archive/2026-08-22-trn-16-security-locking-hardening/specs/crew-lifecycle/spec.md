## MODIFIED Requirements

### Requirement: Crew setup completion is all-or-nothing
The system SHALL only mark a crew "running" after auth injection, config patching, a config-picking-up restart, agent/skill/steering copy, OpenSpec store seeding, and cookie minting have all succeeded, and SHALL clean up the crew if any required step fails. Auth injection SHALL be verified by exit code, not by pattern-matching the output string.

#### Scenario: Successful setup
- **WHEN** a crew has confirmed auth and every setup step (auth inject, config patch, restart, agent/skill/steering copy, OpenSpec seed, model patch, cookie mint) succeeds
- **THEN** the crew is registered with status "running", a gateway URL, and a session cookie

#### Scenario: Cookie mint fails
- **WHEN** every earlier setup step succeeds but minting a session cookie fails
- **THEN** the system tears down the container and both volumes and returns an error rather than registering a crew with no usable cookie

#### Scenario: Auth injection failure is detected
- **WHEN** the auth injection command exits with a non-zero exit code
- **THEN** the system treats the injection as failed, does not proceed with the remaining setup steps, and tears down the partially-created crew

#### Scenario: Auth injection output is not used as a success signal
- **WHEN** the auth injection command exits with a non-zero exit code but its output contains the word "injected"
- **THEN** the system treats the injection as failed, not as successful

## ADDED Requirements

### Requirement: Concurrent login guard is atomic
The system SHALL hold the login-pending lock across both the auth-file guard check and the _login_pending guard check, so that two concurrent POST /login requests cannot both pass both guards and start duplicate login containers.

#### Scenario: Concurrent login requests are serialised
- **WHEN** two POST /login requests arrive simultaneously and no login is in progress
- **THEN** exactly one proceeds to start a login container; the other receives a 409 response indicating a login is already in progress

#### Scenario: Sequential login check is consistent
- **WHEN** a POST /login request checks both the auth-file guard and the login-pending guard
- **THEN** both checks are evaluated while holding the same lock, so a concurrent request cannot slip through between the two checks

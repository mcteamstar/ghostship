# Spec Delta

## MODIFIED Requirements

### Requirement: Credentials resolved at each crew launch
The transport SHALL read a backend's active credential from the store when it launches a crew, not once at startup. A credential stored, replaced or cleared SHALL take effect for the next crew launch without restarting the transport. Running crews SHALL keep their launch-time credential unless a login-flow completion or an explicit operator refresh successfully injects the current flow credential for their recorded backend and profile. Static credentials SHALL remain fixed in the container environment; a changed or replaced static credential or method SHALL require workspace-preserving crew recreation.

#### Scenario: Rotation without restart
- **WHEN** a new claude API key is stored while the transport is running and a claude crew is then launched
- **THEN** the new crew receives the new key, with no transport restart or reinstall

#### Scenario: Logout takes effect at the next launch
- **WHEN** a backend is logged out while one of its crews is running, and a new crew of that backend is then launched
- **THEN** the running crew keeps the credential it already received, and the new crew receives no credential and starts that backend's login instead

#### Scenario: Flow credential refresh applies to matching running crew
- **WHEN** a login-flow credential completes or an operator refreshes a crew assigned to that backend and profile
- **THEN** the current flow credential is injected into that running crew
- **AND** crews assigned to a different backend or profile are not modified

#### Scenario: Changed static credential requires recreation
- **WHEN** a stored static credential or its method changes after a crew container was created
- **THEN** the existing container keeps its launch-time environment and the operator is told that the crew must be recreated with its workspace preserved

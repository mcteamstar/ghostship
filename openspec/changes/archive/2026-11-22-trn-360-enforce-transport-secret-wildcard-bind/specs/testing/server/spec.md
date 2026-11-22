# Spec Delta

## ADDED Requirements

### Requirement: Missing-secret bind guard has bind-class regression coverage
Server tests SHALL verify the missing-transport-secret startup guard for wildcard, specific external, and loopback bind addresses with the guard enabled and disabled.

#### Scenario: Wildcard bind is refused when the guard is enabled
- **WHEN** the transport secret is absent, the bind address is wildcard, and the guard is enabled
- **THEN** the test verifies startup is refused

#### Scenario: Wildcard bind warns when the guard is disabled
- **WHEN** the transport secret is absent, the bind address is wildcard, and the guard is disabled
- **THEN** the test verifies startup continues with a critical warning

#### Scenario: Loopback bind remains allowed without a secret
- **WHEN** the transport secret is absent and the bind address is loopback
- **THEN** the test verifies startup is not refused by the external-bind guard

#### Scenario: A configured secret permits wildcard bind
- **WHEN** a wildcard bind has a transport secret configured
- **THEN** the test verifies the missing-secret guard does not refuse startup

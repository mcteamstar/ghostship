# Spec Delta

## ADDED Requirements

### Requirement: Launch response reports the resolved credential profile

A successful crew launch SHALL return its resolved `acp_profile`, matching the credential profile recorded for the crew, whether selected explicitly or resolved implicitly.

#### Scenario: Explicit named profile
- **WHEN** a crew launches successfully with a named credential profile
- **THEN** the launch response and crew registry identify that same profile

#### Scenario: Implicit profile selection
- **WHEN** a crew launches successfully with an implicitly resolved profile
- **THEN** the launch response reports the actual resolved profile

### Requirement: OAuth credential payloads are isolated by profile

OAuth credentials used for launch, refresh and propagation to existing crews SHALL come from the resolved backend and profile. A named profile SHALL NOT silently receive another profile's credential or a shared default archive. Supported legacy default-profile credentials SHALL remain usable through a safe, idempotent migration or explicit default-only compatibility path.

#### Scenario: Two OAuth profiles
- **WHEN** two profiles of the same backend contain distinct OAuth payloads and a crew selects one
- **THEN** only the selected profile's payload is injected into that crew

#### Scenario: Reauthentication targets one profile
- **WHEN** an OAuth login or refresh completes for one profile
- **THEN** other profiles and crews assigned to them retain their credentials

#### Scenario: Named profile lacks a usable credential
- **WHEN** a named profile has no valid stored payload
- **THEN** the operation reports an error without falling back to a shared or default credential

#### Scenario: Existing legacy default credential
- **WHEN** an operator has only a supported legacy default OAuth credential
- **THEN** the default profile can use it without overwriting a newer profile-scoped credential

### Requirement: OAuth login persistence failures are visible

The system SHALL report OAuth login success only after the selected profile's credential has been durably stored. If persistence fails, the system SHALL report failure and retain enough pending state to retry or explicitly recover, without leaking credentials or claiming completion.

#### Scenario: Profile write fails
- **WHEN** the selected profile credential cannot be saved after OAuth completes
- **THEN** login reports an error rather than success and does not replace another profile's credential

#### Scenario: Retry after transient failure
- **WHEN** the profile write succeeds on a subsequent retry of the same valid pending flow
- **THEN** login reports success and the credential belongs only to the selected profile

# Profile Selection Specification

## Purpose

Governs how a named credential profile is selected when launching a crew, so
the right credential is injected and the registry records which profile was used
for subsequent operations such as post-login auth injection.

## Requirements

### Requirement: launch accepts an optional profile parameter

The `launch` MCP tool SHALL accept an optional `profile` parameter that names
the credential profile to use for the crew's backend. An empty or absent
`profile` triggers implicit resolution.

#### Scenario: Named profile used at launch
- **WHEN** `launch(crew_id="x", backend="kiro", profile="corp")` is called and `kiro/corp` is stored
- **THEN** the crew is started with the `kiro/corp` credential injected
- **AND** no authentication error is returned

#### Scenario: Profile param absent follows implicit resolution
- **WHEN** `launch(crew_id="x", backend="kiro")` is called with no `profile` param
- **THEN** implicit resolution determines the profile (see Requirement: Implicit profile resolution)

### Requirement: Implicit profile resolution

When no profile is specified for `launch`, the system SHALL select the profile
implicitly: if exactly one profile exists for the backend, that profile is used;
otherwise the `default` profile is used.

#### Scenario: Single profile selected implicitly
- **WHEN** `launch` is called without `profile` and only `kiro/corp` exists (no `kiro/default`)
- **THEN** `kiro/corp` is selected and injected

#### Scenario: Default selected when multiple profiles exist
- **WHEN** `launch` is called without `profile` and both `kiro/default` and `kiro/corp` exist
- **THEN** `kiro/default` is selected

#### Scenario: Missing default profile is an authentication error
- **WHEN** `launch` is called without `profile`, `kiro/corp` and `kiro/work` both exist (no single implicit)
- **AND** `kiro/default` does not exist
- **THEN** an `not_authenticated` error is returned describing the available profiles

### Requirement: Resolved profile is recorded in the crew registry

When a crew is successfully launched, the system SHALL record the resolved
`acp_profile` value in the crew registry entry alongside `acp_backend`.

#### Scenario: Profile stored in registry entry
- **WHEN** `launch` succeeds with `backend="kiro"` and `profile="corp"`
- **THEN** the crew's registry entry contains `"acp_profile": "corp"`

#### Scenario: Default profile recorded when omitted
- **WHEN** `launch` succeeds without an explicit `profile`
- **THEN** the crew's registry entry contains `"acp_profile": "<resolved-profile>"`
  where `<resolved-profile>` is the result of implicit resolution

### Requirement: crews() exposes acp_profile

The `crews()` MCP tool and the `GET /api/crews` REST endpoint SHALL include
`acp_profile` in each crew entry returned.

#### Scenario: acp_profile visible in fleet listing
- **WHEN** `crews()` is called after launching two crews with different profiles
- **THEN** each crew entry contains an `acp_profile` field matching what was recorded at launch

#### Scenario: Legacy crew without acp_profile field uses default
- **WHEN** a crew registry entry predates profile support and has no `acp_profile` field
- **THEN** `crews()` returns `"acp_profile": "default"` for that entry

### Requirement: Post-login credential injection is filtered by acp_profile

When a login flow completes and credentials are refreshed, the system SHALL inject
the new credential only into running crews whose `acp_backend` matches the
backend AND whose `acp_profile` matches the profile used by the completed login.

#### Scenario: Injection targets only matching-profile crews
- **WHEN** `kiro/corp` device-flow login completes
- **THEN** only running kiro crews whose `acp_profile` is `"corp"` receive the refreshed credential
- **AND** running kiro crews with `acp_profile` `"default"` are not modified

#### Scenario: No matching crews means no injection
- **WHEN** a `kiro/corp` login completes and no running kiro crew has `acp_profile="corp"`
- **THEN** no inject operation is attempted and the login still succeeds

### Requirement: Missing profile credential triggers the backend's auth flow

When `launch` is called with a profile that has no stored credential, the system
SHALL initiate the backend's authentication flow and return `not_authenticated`,
just as it does when no credential exists at all. The response SHALL name the
profile that is missing.

#### Scenario: Named missing profile triggers auth flow
- **WHEN** `launch(crew_id="x", backend="kiro", profile="corp")` is called and `kiro/corp` is absent
- **THEN** the kiro device flow is initiated and `not_authenticated` is returned
- **AND** the response references the `corp` profile or the login URL

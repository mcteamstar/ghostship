# Spec Delta

## MODIFIED Requirements

### Requirement: GA_CREW_ACP_BACKEND selects the agent runtime
The transport SHALL use the scalar backend default resolved from `backends.default`
for new crews launched without a `backend` argument, defaulting to built-in Kiro.
Kiro is always enabled; Claude and Codex are enabled by their backend sections. The
per-backend model settings applied to a crew SHALL come from that crew's backend.

#### Scenario: Scalar default selects runtime
- **WHEN** `backends.default: claude` and `backends.claude` are configured and a crew is launched without `backend`
- **THEN** the crew SHALL use Claude and record `acp_backend: "claude"`

#### Scenario: Explicit enabled backend overrides default
- **WHEN** Claude is the default, `backends.kiro` is configured, and `launch(..., backend="kiro")` is called
- **THEN** the crew SHALL use Kiro and receive Kiro's backend model settings

#### Scenario: Explicit absent backend is rejected
- **WHEN** `launch(..., backend="codex")` is called and `backends.codex` is absent
- **THEN** launch SHALL return an error naming Codex and the configured enabled backends without creating a crew

#### Scenario: Default backend is kiro
- **WHEN** `backends.default: kiro` and `backends.kiro` are configured and a crew is launched without a backend argument
- **THEN** the crew SHALL use Kiro

#### Scenario: Claude backend selected
- **WHEN** `backends.default: claude` and `backends.claude` are configured and a crew is launched without a backend argument
- **THEN** the crew SHALL use Claude

#### Scenario: Codex backend selected
- **WHEN** `backends.default: codex` and `backends.codex` are configured and a crew is launched without a backend argument
- **THEN** the crew SHALL use Codex

#### Scenario: Per-backend model settings follow the crew
- **WHEN** backend model settings differ and a crew is launched with an explicit backend
- **THEN** the crew SHALL receive the settings for its selected backend

#### Scenario: Invalid backend value is rejected at startup
- **WHEN** the scalar default names an unrecognised backend
- **THEN** startup SHALL reject the configuration rather than launching with an unknown backend

### Requirement: Requested backend must be enabled
The backend requested from `launch` SHALL be present in the enabled backend set
derived from backend configuration sections, with Kiro always included as the
built-in backend. A missing optional backend section SHALL not be treated as enabled
merely because the backend name is supported.

#### Scenario: Absent backend request fails
- **WHEN** only `backends.claude` is configured and `launch(crew_id="a", backend="codex")` is called
- **THEN** launch SHALL return an error and create no container, volume, or registry entry

#### Scenario: Present backend request succeeds past enablement validation
- **WHEN** `backends.claude` and `backends.kiro` are configured and `launch(crew_id="a", backend="kiro")` is called
- **THEN** Kiro SHALL pass backend enablement validation and launch authentication/credential checks

#### Scenario: Disabled backend requested
- **WHEN** only `backends.claude` is configured and `launch(crew_id="a", backend="codex")` is called
- **THEN** launch SHALL return an error and create no crew

#### Scenario: Unknown backend requested
- **WHEN** `launch(crew_id="a", backend="gemini")` is called
- **THEN** launch SHALL return an error listing the enabled backends and create no crew

#### Scenario: Kiro is always launchable
- **WHEN** `backends.kiro` is absent and `launch(crew_id="a", backend="kiro")` is called
- **THEN** launch SHALL accept Kiro as the built-in enabled backend, subject to authentication

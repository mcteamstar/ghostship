# Spec Delta

## MODIFIED Requirements

### Requirement: GA_AGENT_BACKENDS selects the enabled agent backends
The transport SHALL derive the enabled backend set from the resolved backend
configuration sections. Valid backend names are `kiro`, `claude`, and `codex`.
Kiro SHALL always be included; Claude and Codex SHALL be included only when their
corresponding backend sections are configured. The set SHALL preserve no fallback
meaning from list ordering.

#### Scenario: Configured sections define enabled set
- **WHEN** the resolved configuration contains `backends.kiro` and `backends.claude` but no `backends.codex`
- **THEN** the enabled set SHALL be `{kiro, claude}`

#### Scenario: Backend section absent
- **WHEN** `backends.codex` is absent from the resolved configuration
- **THEN** Codex SHALL not be bundled, enabled, or accepted by backend-specific launch and login operations

#### Scenario: Unknown backend section rejected
- **WHEN** the configuration contains `backends.gemini`
- **THEN** install.sh SHALL reject or clearly warn about the unknown backend rather than bundling it

#### Scenario: Default set is kiro only
- **WHEN** neither optional backend section is configured
- **THEN** the enabled set SHALL be `{kiro}`, with no Claude or Codex backend enabled

#### Scenario: Multiple backends enabled
- **WHEN** `backends.claude` and `backends.codex` are configured
- **THEN** the enabled set SHALL be `{claude, codex}`

#### Scenario: Empty entries, duplicates and case are normalised
- **WHEN** backend configuration is normalized from repeated or case-varied entries
- **THEN** the enabled set SHALL contain each configured supported backend once

#### Scenario: Unknown backend name rejected at startup
- **WHEN** an unsupported backend section is present
- **THEN** configuration validation SHALL reject it naming the unknown value and valid names

### Requirement: Kiro is always enabled
The Kiro backend SHALL remain implicitly enabled as the built-in backend, regardless
of whether `backends.kiro` has an explicit configuration section.

#### Scenario: Omitting kiro does not disable it
- **WHEN** `backends.kiro` is absent and only `backends.claude` is configured
- **THEN** Kiro SHALL still be bundled and accepted as the built-in enabled backend

#### Scenario: Listing kiro changes nothing
- **WHEN** `backends.kiro` is present
- **THEN** Kiro SHALL be bundled and accepted as an enabled backend

### Requirement: The default backend must be an enabled backend
The scalar `backends.default` SHALL select the default backend for new crews and
SHALL name an enabled backend. If it names an absent optional or unknown backend,
install.sh or transport startup SHALL fail with an actionable error. If omitted, it
SHALL resolve to the built-in Kiro backend.

#### Scenario: Default backend is enabled
- **WHEN** `backends.default: claude` and `backends.claude` are configured
- **THEN** the transport SHALL start and use Claude for launches without an explicit backend

#### Scenario: Default backend is absent
- **WHEN** `backends.default: codex` is configured but `backends.codex` is absent
- **THEN** configuration validation SHALL fail and identify the missing backend section

#### Scenario: Default backend outside the set
- **WHEN** the scalar default names a backend whose section is absent
- **THEN** the transport SHALL raise a configuration error naming the default and enabled backend settings

#### Scenario: Default backend inside the set
- **WHEN** the scalar default names a configured optional backend section or Kiro
- **THEN** the transport SHALL start with that backend as the default

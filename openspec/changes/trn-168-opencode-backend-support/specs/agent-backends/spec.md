## MODIFIED Requirements

### Requirement: GA_AGENT_BACKENDS selects the enabled agent backends

The transport SHALL read `GA_AGENT_BACKENDS` at startup as a comma-separated list of backend names. Valid names are `kiro`, `claude`, `codex` and `opencode`. Names SHALL be matched case-insensitively with surrounding whitespace ignored. Empty entries and duplicates SHALL be ignored. The enabled set SHALL always contain `kiro`, plus each valid name listed.

#### Scenario: Default set is kiro only
- **WHEN** `GA_AGENT_BACKENDS` is unset or empty
- **THEN** the enabled set is `{kiro}`, and no Claude, Codex, or OpenCode login or default backend is accepted

#### Scenario: Multiple backends enabled
- **WHEN** `GA_AGENT_BACKENDS=claude, codex` is set
- **THEN** the enabled set is `{kiro, claude, codex}`

#### Scenario: OpenCode backend enabled
- **WHEN** `GA_AGENT_BACKENDS=opencode` is set
- **THEN** the enabled set is `{kiro, opencode}`

#### Scenario: Empty entries, duplicates and case are normalised
- **WHEN** `GA_AGENT_BACKENDS=" Claude,,claude , CODEX, OpenCode"` is set
- **THEN** the enabled set is `{kiro, claude, codex, opencode}`

#### Scenario: Unknown backend name rejected at startup
- **WHEN** `GA_AGENT_BACKENDS` contains a name outside `kiro`, `claude`, `codex`, `opencode`
- **THEN** the transport raises a `ConfigError` naming the unknown value and the valid names, and does not start

## ADDED Requirements

### Requirement: Login is available for the opencode backend when enabled

`POST /login/opencode` SHALL be available when opencode is enabled. Otherwise it SHALL return HTTP 400 naming `GA_AGENT_BACKENDS` and the install re-run, checked before the body or pending flow, and create no login container. `POST /logout/opencode` SHALL stay available regardless of whether opencode is enabled.

#### Scenario: Login refused when opencode is not enabled
- **WHEN** `GA_AGENT_BACKENDS` does not include `opencode` and `POST /login/opencode` is called
- **THEN** the transport returns HTTP 400 naming `GA_AGENT_BACKENDS`, and no login container is created

#### Scenario: Login allowed when opencode is enabled
- **WHEN** `GA_AGENT_BACKENDS=opencode` and `POST /login/opencode` is called
- **THEN** the OpenCode login flow starts

#### Scenario: Logout works when opencode is not enabled
- **WHEN** opencode is not enabled, `ga-opencode-auth` exists, and `POST /logout/opencode` is called
- **THEN** `ga-opencode-auth` is deleted

# Spec Delta

## MODIFIED Requirements

### Requirement: Settings for disabled backends are reported as inert

Once per transport start, the transport SHALL log one warning per inert setting: `ANTHROPIC_BASE_URL` while claude is disabled, `OPENAI_BASE_URL` while codex is disabled, and a stored credential for any disabled backend. Each warning SHALL name the setting or backend and method and SHALL NOT include any value. Inert settings SHALL NOT change behaviour.

#### Scenario: Credential for a disabled backend warns without its value
- **WHEN** claude holds a stored `api-key` credential and claude is not enabled
- **THEN** the transport logs a warning that the stored claude credential (api-key) has no effect, the log does not contain the key's value, and startup continues

#### Scenario: Each warning is logged once per start
- **WHEN** the transport starts with `OPENAI_BASE_URL` set and codex disabled
- **THEN** exactly one warning naming `OPENAI_BASE_URL` is logged for that start, regardless of how many modules load the configuration

#### Scenario: No warning for an enabled backend
- **WHEN** claude holds a stored credential and claude is enabled
- **THEN** no inert-setting warning is logged for it

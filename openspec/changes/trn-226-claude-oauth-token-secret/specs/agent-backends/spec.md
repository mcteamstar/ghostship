# Spec Delta

## MODIFIED Requirements

### Requirement: Settings for disabled backends are reported as inert

Once per transport start, the transport SHALL log one warning per inert setting: the `ANTHROPIC_*` settings while claude is disabled, the `OPENAI_*` settings while codex is disabled, and a stored `ga-claude-auth` or `ga-codex-auth` for a disabled backend. Each warning SHALL name the setting and SHALL NOT include its value. Inert settings SHALL NOT change behaviour.

#### Scenario: Credential for a disabled backend warns without its value
- **WHEN** `ANTHROPIC_API_KEY` is set and claude is not enabled
- **THEN** the transport logs a warning naming `ANTHROPIC_API_KEY` as having no effect, the log does not contain the key's value, and startup continues

#### Scenario: Each warning is logged once per start
- **WHEN** the transport starts with `OPENAI_API_KEY` set and codex disabled
- **THEN** exactly one warning naming `OPENAI_API_KEY` is logged for that start, regardless of how many modules load the configuration

#### Scenario: No warning for an enabled backend
- **WHEN** `ANTHROPIC_API_KEY` is set and claude is enabled
- **THEN** no inert-setting warning is logged for it

# Spec Delta

## ADDED Requirements

### Requirement: Claude backend requires a stored credential

A Claude-backend crew SHALL require claude to hold an active credential in the credential store, of any method (`oauth`, `api-key` or `setup-token`), by the time `launch` is called. Without one, launch SHALL start the Claude authorisation-code flow (backend-credentials). The transport SHALL NOT enforce this at startup.

#### Scenario: No Claude credential
- **WHEN** a claude crew is launched and claude holds no credential
- **THEN** `launch` starts the Claude authorisation-code flow, returns `not_authenticated` with its `login_url`, and creates no crew container

#### Scenario: Any Claude method satisfies launch
- **WHEN** a claude crew is launched and claude's active method is `api-key`, `setup-token` or `oauth`
- **THEN** `launch` proceeds and the crew receives that credential only

#### Scenario: Missing credential does not fail at transport startup
- **WHEN** claude is enabled, holds no credential, and the transport starts
- **THEN** the transport starts successfully; the check is deferred to `launch` time

### Requirement: Codex backend requires a stored credential

A Codex-backend crew SHALL require codex to hold an active credential (`api-key` or `chatgpt`) in the credential store by the time `launch` is called. Without one, launch SHALL start the Codex ChatGPT device-code flow (backend-credentials). The transport SHALL NOT enforce this at startup.

#### Scenario: API key stored
- **WHEN** a codex crew is launched and codex holds an `api-key` credential
- **THEN** `launch` proceeds and the key is injected as `OPENAI_API_KEY` into the crew container

#### Scenario: ChatGPT credential stored
- **WHEN** a codex crew is launched and codex holds a `chatgpt` credential
- **THEN** `launch` proceeds and the stored `auth.json` is installed in the crew's `~/.codex/`

#### Scenario: No Codex credential
- **WHEN** a codex crew is launched and codex holds no credential
- **THEN** `launch` starts the ChatGPT device-code flow, returns `not_authenticated` with its `login_url` and `code`, and creates no crew container

#### Scenario: Missing credential does not fail at transport startup
- **WHEN** codex is enabled, holds no credential, and the transport starts
- **THEN** the transport starts successfully; the check is deferred to `launch` time

## REMOVED Requirements

### Requirement: Claude backend requires ANTHROPIC_API_KEY
**Reason**: Replaced by "Claude backend requires a stored credential": any stored Claude method satisfies launch, and the precedence chain is gone.
**Migration**: None.

### Requirement: Codex backend requires an OpenAI credential
**Reason**: Replaced by "Codex backend requires a stored credential": either stored codex method satisfies launch, and the login started on launch is the ChatGPT device-code flow.
**Migration**: None.

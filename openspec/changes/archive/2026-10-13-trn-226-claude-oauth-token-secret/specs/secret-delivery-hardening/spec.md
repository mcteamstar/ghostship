# Spec Delta

## ADDED Requirements

### Requirement: Claude OAuth token is delivered as a Podman secret
`CLAUDE_CODE_OAUTH_TOKEN` SHALL be delivered to `ga-transport` via Podman secret `ga-claude-code-oauth-token` mounted at `/run/secrets/ga-claude-code-oauth-token`. It SHALL NOT appear as plaintext in the `environment:` block of `compose.yml`. The transport SHALL read it from the secret file at startup.

#### Scenario: Claude OAuth token delivered via Podman secret
- **GIVEN** `CLAUDE_CODE_OAUTH_TOKEN` is set in `ghostship.conf`
- **WHEN** `install.sh` runs
- **THEN** the Podman secret `ga-claude-code-oauth-token` exists, `compose.yml` lists it under `ga-transport`'s `secrets:`, and `CLAUDE_CODE_OAUTH_TOKEN` is absent from the `environment:` block

#### Scenario: Claude OAuth token absent, no dangling secret reference
- **GIVEN** `CLAUDE_CODE_OAUTH_TOKEN` is not set
- **WHEN** `install.sh` runs
- **THEN** no `ga-claude-code-oauth-token` secret exists and `compose.yml` does not reference it in either the service `secrets:` list or the top-level `secrets:` block

#### Scenario: Operator's shell token not picked up
- **GIVEN** `CLAUDE_CODE_OAUTH_TOKEN` is exported in the shell that runs `install.sh` and is not set in `ghostship.conf`
- **WHEN** `install.sh` runs
- **THEN** no `ga-claude-code-oauth-token` secret is created and `compose.yml` does not reference it

#### Scenario: Token rotated on reinstall
- **GIVEN** `ga-claude-code-oauth-token` exists from a previous install and `CLAUDE_CODE_OAUTH_TOKEN` now holds a new value
- **WHEN** `install.sh` runs
- **THEN** the secret holds the new value and the transport uses it for crews launched afterwards

#### Scenario: Transport reads the token from the secret file
- **GIVEN** `/run/secrets/ga-claude-code-oauth-token` is present inside `ga-transport`
- **WHEN** the transport starts
- **THEN** the token injected into Claude-backend crews is the value from the secret file

## MODIFIED Requirements

### Requirement: Model API keys are delivered as Podman secrets, not env vars
`ANTHROPIC_API_KEY` and `OPENAI_API_KEY` SHALL be delivered to `ga-transport` via Podman secrets (`ga-crew-anthropic-api-key` and `ga-crew-openai-api-key`) mounted at `/run/secrets/`. They SHALL NOT appear as plaintext in the `environment:` block of `compose.yml`. The transport SHALL read them from the secret files at startup.

#### Scenario: Anthropic key delivered via Podman secret
- **GIVEN** `ANTHROPIC_API_KEY` is set in `ghostship.conf`
- **WHEN** `install.sh` runs
- **THEN** the Podman secret `ga-crew-anthropic-api-key` exists, `compose.yml` lists it under `ga-transport`'s `secrets:`, and `ANTHROPIC_API_KEY` is absent from the `environment:` block

#### Scenario: Anthropic key absent — no dangling secret reference
- **GIVEN** `ANTHROPIC_API_KEY` is not set
- **WHEN** `install.sh` runs
- **THEN** `compose.yml` does not reference `ga-crew-anthropic-api-key` in either the service `secrets:` list or the top-level `secrets:` block

#### Scenario: OpenAI key delivered via Podman secret
- **GIVEN** `OPENAI_API_KEY` is set in `ghostship.conf`
- **WHEN** `install.sh` runs
- **THEN** the Podman secret `ga-crew-openai-api-key` exists and `compose.yml` lists it under `ga-transport`'s `secrets:`

#### Scenario: Transport reads Anthropic key from secret file
- **GIVEN** `/run/secrets/ga-crew-anthropic-api-key` is present inside the `ga-transport` container
- **WHEN** the transport starts
- **THEN** the Anthropic API key used for crew containers is the value from the secret file

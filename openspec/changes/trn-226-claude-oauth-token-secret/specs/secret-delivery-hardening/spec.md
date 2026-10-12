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

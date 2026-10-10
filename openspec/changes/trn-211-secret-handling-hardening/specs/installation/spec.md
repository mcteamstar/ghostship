## Purpose

Defines install.sh behaviour for creating and managing the new Podman secrets
for crew API keys.

## MODIFIED Requirements

### Requirement: install.sh creates Podman secrets for crew API keys

When `GA_CREW_ANTHROPIC_API_KEY`, `GA_CREW_OPENAI_API_KEY`, or `KIRO_API_KEY` are
set, `install.sh` SHALL create corresponding Podman secrets (`ga-crew-anthropic-api-key`,
`ga-crew-openai-api-key`, `ga-kiro-api-key`). Creation SHALL be idempotent: an
existing secret with the same name SHALL be removed before recreation.

#### Scenario: Secret created when key is set

- **GIVEN** `GA_CREW_ANTHROPIC_API_KEY=sk-ant-...` is set in the config
- **WHEN** `install.sh` runs
- **THEN** `podman secret ls` shows `ga-crew-anthropic-api-key` and the install reports "✓ Podman secret 'ga-crew-anthropic-api-key' created"

#### Scenario: Secret not created when key is absent

- **GIVEN** `GA_CREW_ANTHROPIC_API_KEY` is empty or unset
- **WHEN** `install.sh` runs
- **THEN** `podman secret ls` does not show `ga-crew-anthropic-api-key`

#### Scenario: Re-run is idempotent

- **GIVEN** `ga-crew-anthropic-api-key` already exists from a prior run
- **WHEN** `install.sh` runs again with the same or a new key value
- **THEN** the install completes without error and the secret holds the current key value

#### Scenario: Generated compose.yml references new secrets

- **GIVEN** `GA_CREW_ANTHROPIC_API_KEY` and `KIRO_API_KEY` are set
- **WHEN** `install.sh` generates `compose.yml`
- **THEN** `compose.yml` lists `ga-crew-anthropic-api-key` and `ga-kiro-api-key` under `ga-transport`'s `secrets:` and under the top-level `secrets:` block as `external: true`

#### Scenario: Generated compose.yml omits absent-key secrets

- **GIVEN** only `GA_CREW_ANTHROPIC_API_KEY` is set; `GA_CREW_OPENAI_API_KEY` and `KIRO_API_KEY` are unset
- **WHEN** `install.sh` generates `compose.yml`
- **THEN** `compose.yml` references `ga-crew-anthropic-api-key` but does not reference `ga-crew-openai-api-key` or `ga-kiro-api-key`

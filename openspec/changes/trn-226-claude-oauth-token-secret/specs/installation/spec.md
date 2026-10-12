# Spec Delta

## MODIFIED Requirements

### Requirement: Config documentation covers GA_AGENT_BACKENDS

`docs/configuration.md` and `config/ghostship.conf.example` SHALL document `GA_AGENT_BACKENDS`, `GA_CREW_ACP_BACKEND`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `OPENAI_API_KEY` and `OPENAI_BASE_URL`, each with its default, valid values and dependencies, and SHALL NOT document the retired `GA_INCLUDE_*` variables except as removed.

#### Scenario: Config docs cover the consolidated variable
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they find `GA_AGENT_BACKENDS`, `GA_CREW_ACP_BACKEND` and the four `ANTHROPIC_*` and `OPENAI_*` settings documented, each with its default, valid values and which backend it belongs to

### Requirement: install.sh creates Podman secrets for crew API keys
When `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `KIRO_API_KEY` are set, `install.sh` SHALL create corresponding Podman secrets (`ga-crew-anthropic-api-key`, `ga-crew-openai-api-key`, `ga-kiro-api-key`). Creation SHALL be idempotent: an existing secret with the same name SHALL be removed before recreation.

#### Scenario: Secret created when key is set
- **GIVEN** `ANTHROPIC_API_KEY=sk-ant-...` is set in the config
- **WHEN** `install.sh` runs
- **THEN** `podman secret ls` shows `ga-crew-anthropic-api-key` and the install reports "✓ Podman secret 'ga-crew-anthropic-api-key' created"

#### Scenario: Secret not created when key is absent
- **GIVEN** `ANTHROPIC_API_KEY` is empty or unset
- **WHEN** `install.sh` runs
- **THEN** `podman secret ls` does not show `ga-crew-anthropic-api-key`

#### Scenario: Re-run is idempotent
- **GIVEN** `ga-crew-anthropic-api-key` already exists from a prior run
- **WHEN** `install.sh` runs again with the same or a new key value
- **THEN** the install completes without error and the secret holds the current key value

#### Scenario: Generated compose.yml references new secrets
- **GIVEN** `ANTHROPIC_API_KEY` and `KIRO_API_KEY` are set
- **WHEN** `install.sh` generates `compose.yml`
- **THEN** `compose.yml` lists `ga-crew-anthropic-api-key` and `ga-kiro-api-key` under `ga-transport`'s `secrets:` and under the top-level `secrets:` block as `external: true`

#### Scenario: Generated compose.yml omits absent-key secrets
- **GIVEN** only `ANTHROPIC_API_KEY` is set; `OPENAI_API_KEY` and `KIRO_API_KEY` are unset
- **WHEN** `install.sh` generates `compose.yml`
- **THEN** `compose.yml` references `ga-crew-anthropic-api-key` but does not reference `ga-crew-openai-api-key` or `ga-kiro-api-key`

## ADDED Requirements

### Requirement: Model backend settings use their standard names

`install.sh` SHALL read the model backend settings under the names the Claude and Codex CLIs use: `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `OPENAI_API_KEY` and `OPENAI_BASE_URL`. Each SHALL be reset to empty before `ghostship.conf` is sourced, so a value exported in the invoking shell is never used.

#### Scenario: Standard names configure the backends
- **WHEN** `ghostship.conf` sets `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`
- **THEN** `install.sh` delivers them as the `ga-crew-anthropic-api-key` and `ga-crew-openai-api-key` Podman secrets and prints no deprecation warning

#### Scenario: Shell values ignored
- **WHEN** `ANTHROPIC_API_KEY` or `GA_CREW_ANTHROPIC_API_KEY` is exported in the shell running `install.sh` and neither is set in `ghostship.conf`
- **THEN** no `ga-crew-anthropic-api-key` secret is created

### Requirement: Pre-TRN-226 model backend names accepted as deprecated aliases

`install.sh` SHALL accept `GA_CREW_ANTHROPIC_API_KEY`, `GA_CREW_ANTHROPIC_BASE_URL`, `GA_CREW_OPENAI_API_KEY` and `GA_CREW_OPENAI_BASE_URL` from `ghostship.conf` as aliases for the standard names. Each alias in use SHALL print a warning naming the old and new setting, never the value. When both names are set, the standard name SHALL win.

#### Scenario: Old name mapped with a warning
- **WHEN** `ghostship.conf` sets only `GA_CREW_ANTHROPIC_API_KEY`
- **THEN** `install.sh` uses its value as `ANTHROPIC_API_KEY` and warns that `GA_CREW_ANTHROPIC_API_KEY` is deprecated, without printing the value

#### Scenario: Standard name wins
- **WHEN** `ghostship.conf` sets both `ANTHROPIC_API_KEY` and `GA_CREW_ANTHROPIC_API_KEY`
- **THEN** `install.sh` uses `ANTHROPIC_API_KEY` and warns that the old name is ignored

## Purpose

Defines how model API keys and the kiro API key are delivered to the transport
container — via Podman secrets rather than compose environment variables.

## MODIFIED Requirements

### Requirement: Model API keys are delivered as Podman secrets, not env vars

`GA_CREW_ANTHROPIC_API_KEY` and `GA_CREW_OPENAI_API_KEY` SHALL be delivered to
`ga-transport` via Podman secrets (`ga-crew-anthropic-api-key` and
`ga-crew-openai-api-key`) mounted at `/run/secrets/`. They SHALL NOT appear as
plaintext in the `environment:` block of `compose.yml`. The transport SHALL read
them from the secret files at startup.

#### Scenario: Anthropic key delivered via Podman secret

- **GIVEN** `GA_CREW_ANTHROPIC_API_KEY` is set in `ghostship.conf`
- **WHEN** `install.sh` runs
- **THEN** the Podman secret `ga-crew-anthropic-api-key` exists, `compose.yml` lists it under `ga-transport`'s `secrets:`, and `GA_CREW_ANTHROPIC_API_KEY` is absent from the `environment:` block

#### Scenario: Anthropic key absent — no dangling secret reference

- **GIVEN** `GA_CREW_ANTHROPIC_API_KEY` is not set
- **WHEN** `install.sh` runs
- **THEN** `compose.yml` does not reference `ga-crew-anthropic-api-key` in either the service `secrets:` list or the top-level `secrets:` block

#### Scenario: OpenAI key delivered via Podman secret

- **GIVEN** `GA_CREW_OPENAI_API_KEY` is set in `ghostship.conf`
- **WHEN** `install.sh` runs
- **THEN** the Podman secret `ga-crew-openai-api-key` exists and `compose.yml` lists it under `ga-transport`'s `secrets:`

#### Scenario: Transport reads Anthropic key from secret file

- **GIVEN** `/run/secrets/ga-crew-anthropic-api-key` is present inside the `ga-transport` container
- **WHEN** the transport starts
- **THEN** the Anthropic API key used for crew containers is the value from the secret file

## ADDED Requirements

### Requirement: KIRO_API_KEY is delivered as a Podman secret

`KIRO_API_KEY` SHALL be delivered to `ga-transport` via Podman secret
`ga-kiro-api-key` mounted at `/run/secrets/ga-kiro-api-key`. It SHALL NOT appear
as a plaintext environment variable in `compose.yml`. The transport SHALL read it
from the secret file at startup and use it to authenticate kiro-cli in crew
containers (headless / Pro+ API-key path). When the secret is absent, the
transport SHALL fall back to the device-code auth flow unchanged.

#### Scenario: KIRO_API_KEY delivered via Podman secret

- **GIVEN** `KIRO_API_KEY` is set in `ghostship.conf`
- **WHEN** `install.sh` runs
- **THEN** the Podman secret `ga-kiro-api-key` exists, `compose.yml` lists it under `ga-transport`'s `secrets:`, and `KIRO_API_KEY` does not appear in the `environment:` block

#### Scenario: KIRO_API_KEY absent — device-code fallback unchanged

- **GIVEN** `KIRO_API_KEY` is not set
- **WHEN** `install.sh` runs and `ga-transport` starts
- **THEN** `compose.yml` does not reference `ga-kiro-api-key` and the transport uses the device-code auth flow

#### Scenario: Transport reads kiro key from secret file

- **GIVEN** `/run/secrets/ga-kiro-api-key` is present inside `ga-transport`
- **WHEN** the transport starts
- **THEN** `KIRO_API_KEY` injected into crew containers is the value from the secret file, and the device-code flow is skipped

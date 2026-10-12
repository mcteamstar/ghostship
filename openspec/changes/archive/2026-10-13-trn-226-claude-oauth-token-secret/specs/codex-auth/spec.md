# Spec Delta

## MODIFIED Requirements

### Requirement: Codex credential is injected into crew containers at launch

When `GA_CREW_ACP_BACKEND=codex` and `ga-codex-auth` is the active credential source, the transport SHALL inject the archived `~/.codex/` contents into the crew container's `/home/kirocrew/.codex/` at launch time, matching the path the `codex-acp` adapter reads for credentials.

#### Scenario: OAuth credential injected on launch
- **WHEN** a Codex-backend crew is launched, `OPENAI_API_KEY` is unset, and `ga-codex-auth` exists and is non-empty
- **THEN** the transport untars `ga-codex-auth` into the crew container's `/home/kirocrew/.codex/` before the gateway starts

#### Scenario: API key takes precedence over OAuth credential
- **WHEN** a Codex-backend crew is launched and `OPENAI_API_KEY` is set
- **THEN** the transport injects `OPENAI_API_KEY` as an env var and does not inject the `ga-codex-auth` archive

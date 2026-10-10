## ADDED Requirements

### Requirement: spec-ops image conditionally includes Codex toolchain

The spec-ops `Containerfile` SHALL install the `codex-acp` adapter (npm package `@agentclientprotocol/codex-acp`) when the `INCLUDE_CODEX_AGENT` build arg is set to `true`. This is ONE component, not two: the adapter ships its own compatible Codex binary, so — unlike the Claude toolchain — no separate `codex` CLI is installed. The toolchain SHALL NOT be installed by default, to keep the baseline image lean.

The installed version SHALL be pinned (an exact version tag, not a floating range) in the Containerfile.

#### Scenario: Default image build does not include Codex toolchain
- **WHEN** `install.sh` runs without `GA_INCLUDE_CODEX_AGENT=true`
- **THEN** the built spec-ops image does not contain the `codex-acp` adapter

#### Scenario: Codex-enabled image build
- **WHEN** the spec-ops image is built with `INCLUDE_CODEX_AGENT=true`
- **THEN** the resulting image contains the `codex-acp` adapter (pinned npm package) resolvable on the crew's PATH

#### Scenario: Pinned version in Containerfile
- **WHEN** `crews/spec-ops/Containerfile` is read
- **THEN** the Codex toolchain install step references an exact version tag, not `latest` or a floating range

### Requirement: GA_INCLUDE_CODEX_AGENT enables Codex toolchain at install time

`install.sh` SHALL pass `INCLUDE_CODEX_AGENT=true` as a build arg to the spec-ops image build when `GA_INCLUDE_CODEX_AGENT=true` is resolved from the config file. `docs/configuration.md` and `config/ghostship.conf.example` SHALL document `GA_INCLUDE_CODEX_AGENT`, the `"codex"` value of `GA_CREW_ACP_BACKEND`, `GA_CREW_OPENAI_API_KEY`, and `GA_CREW_OPENAI_BASE_URL`.

#### Scenario: Config enables Codex toolchain
- **WHEN** `GA_INCLUDE_CODEX_AGENT=true` is set in `ghostship.conf` and `install.sh` runs
- **THEN** the spec-ops image build receives `--build-arg INCLUDE_CODEX_AGENT=true`

#### Scenario: Config docs cover all new Codex env vars
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they find documented entries for `GA_INCLUDE_CODEX_AGENT`, the `"codex"` value of `GA_CREW_ACP_BACKEND`, `GA_CREW_OPENAI_API_KEY`, and `GA_CREW_OPENAI_BASE_URL`, each with its default, valid values, and any dependencies between them

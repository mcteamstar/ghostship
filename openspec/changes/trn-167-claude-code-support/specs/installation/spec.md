## ADDED Requirements

### Requirement: spec-ops image conditionally includes Claude Code toolchain

The spec-ops `Containerfile` SHALL install `claude-agent-acp` (npm package) and the `claude` CLI when the `INCLUDE_CLAUDE_AGENT` build arg is set to `true`. The toolchain SHALL NOT be installed by default, to keep the baseline image lean.

The installed versions SHALL be pinned (exact version tags, not floating) in the Containerfile.

#### Scenario: Default image build does not include Claude toolchain
- **WHEN** `install.sh` runs without `GA_INCLUDE_CLAUDE_AGENT=true`
- **THEN** the built spec-ops image does not contain `claude-agent-acp` or `claude` CLI

#### Scenario: Claude-enabled image build
- **WHEN** the spec-ops image is built with `INCLUDE_CLAUDE_AGENT=true`
- **THEN** the resulting image contains `claude-agent-acp` (pinned npm package) and the `claude` CLI binary at a known, pinned version

#### Scenario: Pinned versions in Containerfile
- **WHEN** `crews/spec-ops/Containerfile` is read
- **THEN** the Claude toolchain install step references exact version tags, not `latest` or floating ranges

### Requirement: GA_INCLUDE_CLAUDE_AGENT enables Claude toolchain at install time

`install.sh` SHALL pass `INCLUDE_CLAUDE_AGENT=true` as a build arg to the spec-ops image build when `GA_INCLUDE_CLAUDE_AGENT=true` is resolved from the config file. `docs/configuration.md` and `config/ghostship.conf.example` SHALL document `GA_INCLUDE_CLAUDE_AGENT` and `GA_CREW_ACP_BACKEND` and `GA_CREW_ANTHROPIC_API_KEY`.

#### Scenario: Config enables Claude toolchain
- **WHEN** `GA_INCLUDE_CLAUDE_AGENT=true` is set in `ghostship.conf` and `install.sh` runs
- **THEN** the spec-ops image build receives `--build-arg INCLUDE_CLAUDE_AGENT=true`

#### Scenario: Config docs cover all three new env vars
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they find documented entries for `GA_INCLUDE_CLAUDE_AGENT`, `GA_CREW_ACP_BACKEND`, and `GA_CREW_ANTHROPIC_API_KEY` with their defaults, valid values, and any dependencies between them

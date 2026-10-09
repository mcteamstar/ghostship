# Spec Delta

## MODIFIED Requirements

### Requirement: spec-ops image conditionally includes Claude Code toolchain

The spec-ops image SHALL include `claude-agent-acp` (npm package) and the `claude` CLI when `claude` is a member of the enabled backend set. They SHALL be installed by the toolchain script `crews/spec-ops/toolchains/claude.sh`, which the image build runs only when `claude` appears in the `AGENT_TOOLCHAINS` build arg. The toolchain SHALL NOT be installed by default, to keep the baseline image lean.

The installed versions SHALL be pinned (exact version tags, not floating) in the Claude toolchain script.

#### Scenario: Default image build does not include Claude toolchain
- **WHEN** `install.sh` runs and `GA_AGENT_BACKENDS` does not list `claude`
- **THEN** the built spec-ops image does not contain `claude-agent-acp` or `claude` CLI

#### Scenario: Claude-enabled image build
- **WHEN** the spec-ops image is built with `AGENT_TOOLCHAINS` containing `claude`
- **THEN** the resulting image contains `claude-agent-acp` (pinned npm package) and the `claude` CLI binary at a known, pinned version

#### Scenario: Pinned versions in Containerfile
- **WHEN** `crews/spec-ops/toolchains/claude.sh` is read
- **THEN** its install steps reference exact version tags, not `latest` or floating ranges

### Requirement: spec-ops image conditionally includes Codex toolchain

The spec-ops image SHALL include the `codex-acp` adapter (npm package `@agentclientprotocol/codex-acp`) when `codex` is a member of the enabled backend set. It SHALL be installed by the toolchain script `crews/spec-ops/toolchains/codex.sh`, which the image build runs only when `codex` appears in the `AGENT_TOOLCHAINS` build arg. This is ONE component, not two: the adapter ships its own compatible Codex binary, so no separate `codex` CLI is installed. The toolchain SHALL NOT be installed by default, to keep the baseline image lean.

The installed version SHALL be pinned (an exact version tag, not a floating range) in the Codex toolchain script.

#### Scenario: Default image build does not include Codex toolchain
- **WHEN** `install.sh` runs and `GA_AGENT_BACKENDS` does not list `codex`
- **THEN** the built spec-ops image does not contain the `codex-acp` adapter

#### Scenario: Codex-enabled image build
- **WHEN** the spec-ops image is built with `AGENT_TOOLCHAINS` containing `codex`
- **THEN** the resulting image contains the `codex-acp` adapter (pinned npm package) resolvable on the crew's PATH

#### Scenario: Pinned version in Containerfile
- **WHEN** `crews/spec-ops/toolchains/codex.sh` is read
- **THEN** its install step references an exact version tag, not `latest` or a floating range

## ADDED Requirements

### Requirement: GA_AGENT_BACKENDS drives toolchain inclusion at install time

`install.sh` SHALL pass one build arg, `AGENT_TOOLCHAINS`, to the spec-ops image build: the normalised members of `GA_AGENT_BACKENDS` other than kiro, comma-separated. Each listed name SHALL match `^[a-z][a-z0-9-]*$` and be `kiro` or the basename of a script in `crews/spec-ops/toolchains/`; otherwise `install.sh` SHALL exit before building. Enabling an available backend SHALL need only a config change and an install run.

#### Scenario: Set enables the Claude toolchain
- **WHEN** `GA_AGENT_BACKENDS=claude` is set in `ghostship.conf` and `install.sh` runs
- **THEN** the spec-ops image build receives `--build-arg AGENT_TOOLCHAINS=claude`

#### Scenario: Set enables several toolchains
- **WHEN** `GA_AGENT_BACKENDS=claude,codex` is set and `install.sh` runs
- **THEN** the image build receives `--build-arg AGENT_TOOLCHAINS=claude,codex`

#### Scenario: Kiro-only set builds no optional toolchain
- **WHEN** `GA_AGENT_BACKENDS` is unset and `install.sh` runs
- **THEN** the image build receives `--build-arg AGENT_TOOLCHAINS=` (empty) and no toolchain script runs

#### Scenario: Name without a toolchain script is rejected
- **WHEN** `GA_AGENT_BACKENDS=opencode` is set and `install.sh` runs
- **THEN** `install.sh` exits non-zero before building, naming `opencode` and the available toolchains

#### Scenario: Path-like name is rejected
- **WHEN** `GA_AGENT_BACKENDS=../toolchains/claude` is set and `install.sh` runs
- **THEN** `install.sh` exits non-zero before building, and no script outside `crews/spec-ops/toolchains/` is referenced

### Requirement: Toolchains are defined per backend, not hard-coded in the build

Each optional backend's toolchain SHALL be one script under `crews/spec-ops/toolchains/`, named after the backend. The image build SHALL run the scripts named in `AGENT_TOOLCHAINS` and no others, and SHALL fail if any script fails. The Containerfile SHALL NOT contain per-backend install logic. Adding a new backend's toolchain SHALL NOT change the Containerfile, `install.sh`, or other toolchain scripts.

#### Scenario: Adding a toolchain leaves the build unchanged
- **WHEN** a new backend script is added under `crews/spec-ops/toolchains/`
- **THEN** the Containerfile, `install.sh`, and the Claude and Codex scripts are byte-identical to their previous versions

#### Scenario: Unlisted toolchain contributes nothing
- **WHEN** a backend is not named in `AGENT_TOOLCHAINS`
- **THEN** its script does not run and the image contains none of that toolchain

#### Scenario: A failing toolchain fails the build
- **WHEN** a listed toolchain script exits non-zero
- **THEN** the image build fails and names the failing script

### Requirement: The transport receives the enabled set

`install.sh` SHALL write `GA_AGENT_BACKENDS` into the transport container's environment as the normalised list it used for `AGENT_TOOLCHAINS`: lowercase, comma-separated in first-listed order, without duplicates, without kiro, and empty when only kiro is enabled. It SHALL NOT write `GA_INCLUDE_CLAUDE_AGENT` or `GA_INCLUDE_CODEX_AGENT` into that environment.

#### Scenario: Compose environment carries the set
- **WHEN** `GA_AGENT_BACKENDS=claude` is set and `install.sh` generates the compose file
- **THEN** the transport service environment contains `GA_AGENT_BACKENDS=claude` and contains neither retired variable

#### Scenario: Compose value is normalised
- **WHEN** `GA_AGENT_BACKENDS=" Kiro, CODEX,,claude,codex"` is set and `install.sh` generates the compose file
- **THEN** the transport service environment contains `GA_AGENT_BACKENDS=codex,claude`

#### Scenario: Kiro-only compose value is empty
- **WHEN** `GA_AGENT_BACKENDS` is unset and `install.sh` generates the compose file
- **THEN** the transport service environment contains `GA_AGENT_BACKENDS=` (empty)

### Requirement: Config documentation covers GA_AGENT_BACKENDS

`docs/configuration.md` and `config/ghostship.conf.example` SHALL document `GA_AGENT_BACKENDS`, `GA_CREW_ACP_BACKEND`, `GA_CREW_ANTHROPIC_API_KEY`, `GA_CREW_ANTHROPIC_BASE_URL`, `GA_CREW_OPENAI_API_KEY` and `GA_CREW_OPENAI_BASE_URL`, each with its default, valid values and dependencies, and SHALL NOT document the retired `GA_INCLUDE_*` variables except as removed.

#### Scenario: Config docs cover the consolidated variable
- **WHEN** an operator reads `docs/configuration.md`
- **THEN** they find `GA_AGENT_BACKENDS`, `GA_CREW_ACP_BACKEND` and the four `GA_CREW_ANTHROPIC_*` and `GA_CREW_OPENAI_*` settings documented, each with its default, valid values and which backend it belongs to

### Requirement: install.sh checks the default backend before building

`install.sh` SHALL exit with an error before building any image when `GA_CREW_ACP_BACKEND` is set to a value that is neither `kiro` nor a member of `GA_AGENT_BACKENDS`. The message SHALL name both settings. This catches a configuration the transport would reject at startup, before a full build and a restart loop.

#### Scenario: Default outside the set fails before the build
- **WHEN** `GA_CREW_ACP_BACKEND=codex` and `GA_AGENT_BACKENDS=claude` are set and `install.sh` runs
- **THEN** `install.sh` exits non-zero naming `GA_CREW_ACP_BACKEND` and `GA_AGENT_BACKENDS`, and no image is built

### Requirement: Changing the toolchain list forces a rebuild

The spec-ops image SHALL record its toolchain list in the `org.ghostship.toolchains` label, set from `AGENT_TOOLCHAINS`. When the existing image's label differs from the list `install.sh` is about to build, `install.sh` SHALL build the spec-ops image without the layer cache, so a stale toolchain layer is never reused.

#### Scenario: Adding a toolchain rebuilds without cache
- **WHEN** the existing spec-ops image has `org.ghostship.toolchains=claude` and `install.sh` runs with `GA_AGENT_BACKENDS=claude,codex`
- **THEN** the spec-ops image is built without the layer cache and its label becomes `claude,codex`

#### Scenario: Unchanged list keeps the cache
- **WHEN** the existing image's label equals the new `AGENT_TOOLCHAINS` value and the version is unchanged
- **THEN** `install.sh` does not force a cache-less spec-ops build on account of the toolchains

## REMOVED Requirements

### Requirement: GA_INCLUDE_CLAUDE_AGENT enables Claude toolchain at install time

**Reason**: Dev phase, no compatibility needed. A second variable for the same choice caused the drift this change removes.

**Migration**: Set `GA_AGENT_BACKENDS=claude` in `ghostship.conf` (add `claude` to the list if other backends are enabled), then re-run `ghostship install`. `GA_INCLUDE_CLAUDE_AGENT` now fails startup and install.

### Requirement: GA_INCLUDE_CODEX_AGENT enables Codex toolchain at install time

**Reason**: As above. The set is the single source of truth for optional toolchains.

**Migration**: Set `GA_AGENT_BACKENDS=codex` (or include `codex` in the list), then re-run `ghostship install`. `GA_INCLUDE_CODEX_AGENT` now fails startup and install.

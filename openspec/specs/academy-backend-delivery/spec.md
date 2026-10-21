# academy-backend-delivery Specification

## Purpose
Deliver Academy content (skills, steering, MCP) to the backend-native harness paths of every crew's configured agent runtime, using `mcteamstar/.agents` as the per-backend path and format middleware, so that claude, opencode, and codex backend crews receive the same operational wiring as kiro crews.

## Requirements

### Requirement: .agents baked into every crew image
Every crew image SHALL include `mcteamstar/.agents` cloned into `/home/kirocrew/.agents` at image build time, providing the `setup` script and its per-backend harness path table.

#### Scenario: .agents present after image build
- **WHEN** a crew image is built from any composition Containerfile
- **THEN** `/home/kirocrew/.agents/setup` exists and is executable inside the resulting image

### Requirement: AcademyLoader stages content into .agents directories
At crew launch, `AcademyLoader` SHALL copy manifest-selected Academy skills into `/home/kirocrew/.agents/skills/`, steering docs into `/home/kirocrew/.agents/context/`, and resolved MCP catalogue entries (after env-var substitution) into `/home/kirocrew/.agents/mcp/`, replacing any files previously staged from a prior launch.

#### Scenario: Skills staged before setup runs
- **WHEN** `AcademyLoader` runs for a newly launched crew
- **THEN** each manifest-selected skill directory is present under `/home/kirocrew/.agents/skills/` inside the crew container before `.agents/setup` is called

#### Scenario: Steering staged before setup runs
- **WHEN** `AcademyLoader` runs for a newly launched crew
- **THEN** each manifest-selected steering doc is present under `/home/kirocrew/.agents/context/` inside the crew container before `.agents/setup` is called

### Requirement: AcademyLoader execs .agents/setup for every detected harness
After staging, `AcademyLoader` SHALL exec `.agents/setup` inside the crew container with no harness argument, so that setup wires the staged content to the native paths of every harness it detects in the crew image, not only the crew's own `acp_backend`. Harness detection SHALL be left to `.agents/setup`; ghostship SHALL NOT pass the crew's backend to narrow it.

#### Scenario: kiro harness wired to kiro paths
- **WHEN** `kiro-cli` is present in the crew image and `AcademyLoader` completes, whatever the crew's `acp_backend`
- **THEN** skills are present under `~/.kiro/skills/`, steering docs under `~/.kiro/steering/`, and MCP config written to `~/.kiro/mcp.json`

#### Scenario: claude harness wired to claude paths
- **WHEN** `claude` is present in the crew image and `AcademyLoader` completes, whatever the crew's `acp_backend`
- **THEN** skills are present under `~/.claude/skills/`, steering docs under `~/.claude/rules/`, and MCP config written to `~/.claude.json`

#### Scenario: Setup failure falls back gracefully
- **WHEN** `.agents/setup` exits non-zero
- **THEN** `AcademyLoader` logs a warning and crew launch continues — agents receive no academy wiring rather than failing to launch

### Requirement: MCP delivery remains a launch-time operation
MCP catalogue entries SHALL continue to be resolved and delivered at launch time (not at image build time), because catalogue entries contain `${VAR}` references that require the runtime transport environment.

#### Scenario: MCP env vars resolved at launch
- **WHEN** a catalogue entry references `${NEXUS_API_KEY}` and that variable is set in the transport environment at launch time
- **THEN** the resolved value is written into the backend-native MCP config inside the crew container

### Requirement: Agent persona JSON is delivered for every backend
Manifest-selected agent persona JSON files (`academy/agents/*.json`) SHALL be delivered to `~/.kiro/agents/` for every crew, whatever its `acp_backend`. `~/.kiro/agents/` is KiroCrew's persona registry: the gateway reads it on every backend to resolve named persona dispatch and to build each session's persona prompt. It is not a kiro-cli-only location.

#### Scenario: Persona JSON written for a claude crew
- **WHEN** a crew's `acp_backend` is `claude` and `AcademyLoader` completes
- **THEN** each manifest-selected persona JSON is present in `~/.kiro/agents/`, and a named dispatch such as `ghost` is accepted by the crew gateway

#### Scenario: Persona JSON written for a kiro crew
- **WHEN** a crew's `acp_backend` is `kiro` and `AcademyLoader` completes
- **THEN** each manifest-selected persona JSON is present in `~/.kiro/agents/`

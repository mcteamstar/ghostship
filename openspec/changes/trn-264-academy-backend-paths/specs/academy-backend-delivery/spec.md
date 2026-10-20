# Spec Delta

## Purpose

Deliver Academy content (skills, steering, MCP) to the backend-native harness paths of every crew's configured agent runtime, using `mcteamstar/.agents` as the per-backend path and format middleware, so that claude, opencode, and codex backend crews receive the same operational wiring as kiro crews.

## ADDED Requirements

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

### Requirement: AcademyLoader execs .agents/setup for the crew's backend
After staging, `AcademyLoader` SHALL exec `.agents/setup <backend>` inside the crew container, where `<backend>` is the crew's registered `acp_backend` value (`kiro`, `claude`, or `codex`). Setup SHALL wire the staged content to the backend's native harness paths.

#### Scenario: kiro backend wired to kiro paths
- **WHEN** a crew's `acp_backend` is `kiro` and `AcademyLoader` completes
- **THEN** skills are present under `~/.kiro/skills/`, steering docs under `~/.kiro/steering/`, and MCP config written to `~/.kiro/mcp.json`

#### Scenario: claude backend wired to claude paths
- **WHEN** a crew's `acp_backend` is `claude` and `AcademyLoader` completes
- **THEN** skills are present under `~/.claude/skills/`, steering docs under `~/.claude/rules/`, and MCP config written to `~/.claude.json`

#### Scenario: Unknown backend falls back gracefully
- **WHEN** `.agents/setup` is called with a backend name it does not recognise
- **THEN** setup exits non-zero, `AcademyLoader` logs a warning naming the backend, and crew launch continues — agents receive no academy wiring rather than failing to launch

### Requirement: MCP delivery remains a launch-time operation
MCP catalogue entries SHALL continue to be resolved and delivered at launch time (not at image build time), because catalogue entries contain `${VAR}` references that require the runtime transport environment.

#### Scenario: MCP env vars resolved at launch
- **WHEN** a catalogue entry references `${NEXUS_API_KEY}` and that variable is set in the transport environment at launch time
- **THEN** the resolved value is written into the backend-native MCP config inside the crew container

### Requirement: Agent persona JSON delivery remains kiro-only
Agent persona JSON files (`academy/agents/*.json`) SHALL continue to be delivered only to `~/.kiro/agents/` and only for kiro-backend crews. No persona JSON delivery occurs for claude or codex backend crews.

#### Scenario: Persona JSON not written for claude backend
- **WHEN** a crew's `acp_backend` is `claude` and `AcademyLoader` completes
- **THEN** no files are written to `~/.kiro/agents/` inside the crew container

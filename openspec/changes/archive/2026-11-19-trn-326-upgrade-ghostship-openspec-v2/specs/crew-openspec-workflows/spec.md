# Spec Delta

## Purpose

Defines how Ghostship crews receive and use OpenSpec's shared workflow skills, including the bundled CLI compatibility contract and preservation of project change artifacts.

## ADDED Requirements

### Requirement: Bundled OpenSpec CLI and Academy skills are version-compatible
The spec-ops crew image SHALL bundle the selected OpenSpec v2 CLI, its six core Academy workflow skills, and the optional `openspec-verify-change` skill required by Ghostship's planned hygiene workflow. All bundled Academy skills SHALL be compatible with the selected CLI release.

#### Scenario: Fresh crew receives the paired CLI and skills
- **WHEN** a fresh spec-ops crew finishes setup
- **THEN** its installed OpenSpec CLI reports the selected v2 version and its shared skills include the six core workflows plus the compatible `openspec-verify-change` skill

#### Scenario: Hygiene workflow skill is staged
- **WHEN** a fresh crew finishes Academy skill setup
- **THEN** `openspec-verify-change` is discoverable alongside the six core skills and can verify an implemented change before archival

#### Scenario: Dependency review records the resolved pair
- **WHEN** maintainers review the bundled OpenSpec integration
- **THEN** the dependency inventory and review evidence identify the pinned CLI version, skill source, and compatibility verification

### Requirement: OpenSpec skills are discoverable through backend-supported invocation
OpenSpec workflow guidance shipped by Ghostship SHALL refer to the available `openspec-*` skills and use each backend's supported skill invocation syntax; it SHALL NOT direct agents to removed `/opsx:*` command files.

#### Scenario: Codex agent invokes an OpenSpec skill
- **WHEN** a Codex agent follows a Ghostship OpenSpec instruction
- **THEN** it can identify the skill name and invoke it using Codex's `$openspec-*` syntax

#### Scenario: Slash-command backend invokes an OpenSpec skill
- **WHEN** an agent on a backend that supports slash skill invocation follows a Ghostship OpenSpec instruction
- **THEN** it can identify the skill name and invoke it using the backend's `/openspec-*` syntax

#### Scenario: Removed command files are not presented as available
- **WHEN** an agent reads shipped Ghostship OpenSpec guidance
- **THEN** the instructions do not claim that `/opsx:*` commands are available

### Requirement: Missing optional workflow skills have a CLI instructions fallback
When Ghostship intentionally leaves an optional OpenSpec workflow skill unbundled, its guidance SHALL explain how to obtain and follow that workflow's instructions through the bundled CLI.

#### Scenario: Continue workflow is not packaged
- **WHEN** a crew needs to continue an OpenSpec change and `openspec-continue-change` remains unbundled
- **THEN** its agent can use the bundled CLI's instructions command for the next required artifact and continue the workflow without assuming a skill exists

### Requirement: Existing OpenSpec change artifacts remain usable after the upgrade
Upgrading Ghostship's bundled OpenSpec tooling SHALL preserve existing project change artifacts and their ability to be read and continued with the new CLI and skills.

#### Scenario: Existing change is opened by an upgraded crew
- **WHEN** an upgraded crew receives a project containing an existing OpenSpec change
- **THEN** the bundled CLI can inspect that change and its artifacts remain available for the supported workflow

#### Scenario: Migration output affects existing project files
- **WHEN** migration output proposes changes to existing crew or project files
- **THEN** maintainers review the output before applying it and retain existing project artifacts unless an explicit migration step requires a reviewed change

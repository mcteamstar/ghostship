# Shared OpenSpec Store Specification

## Purpose

Give every agent dispatched into a crew a single shared OpenSpec store to resolve `openspec` commands against, even though each dispatched task runs in its own isolated working directory — so one agent's proposal is visible to another agent implementing it later, with no explicit path-passing required.

## Requirements

### Requirement: Store seeded at workspace root on launch
The system SHALL initialise an OpenSpec store at the crew's workspace root during crew setup, one directory level above every per-task `subagent_*/` directory and as a sibling to (never inside) any delivered `repo/`.

#### Scenario: New crew setup seeds the store
- **WHEN** a crew finishes setup
- **THEN** the system runs `openspec init --tools none --no-animation --force` at the crew's workspace root, creating `openspec/config.yaml`, `openspec/changes/`, and `openspec/specs/` there

#### Scenario: Repeat launch is idempotent
- **WHEN** `_seed_openspec_store` runs again for a crew that already has an OpenSpec store at its workspace root (e.g. on a later launch)
- **THEN** the existing store is left intact rather than duplicated or errored on, because `--force` makes the init call safe to repeat

### Requirement: Per-task directories resolve up to the shared store
The system SHALL rely on OpenSpec's own nearest-ancestor directory resolution — not any explicit configuration passed to dispatched agents — to make every task's `openspec` commands act on the shared workspace-root store.

#### Scenario: Two tasks share OpenSpec state without coordination
- **WHEN** one dispatched task proposes an OpenSpec change and a later, independently dispatched task in the same crew runs `openspec` commands against that change
- **THEN** both tasks resolve to the same `openspec/` store at the workspace root, because each task's own `subagent_*/` directory has no `openspec/` of its own and OpenSpec walks upward to find one

#### Scenario: Store failed to seed
- **WHEN** `openspec init` fails during crew setup (e.g. the CLI errors)
- **THEN** the failure is logged as a warning and crew setup continues; a dispatched task's `openspec` commands would then resolve to whatever `openspec/` root (if any) it can find up its own directory tree, which may not exist

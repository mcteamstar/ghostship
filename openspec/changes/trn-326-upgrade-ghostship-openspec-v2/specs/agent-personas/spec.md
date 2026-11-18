# Spec Delta

## MODIFIED Requirements

### Requirement: OpenSpec workflow division by persona
The system SHALL scope each persona's prompt to the intended OpenSpec explore -> propose -> apply -> archive workflow division: Spectre to explore/propose/update-change, Ghost to all six operations with apply-change as its implementation path, Banshee to explore/propose/update-change/apply-change for independent review and fixes, and Reaper to sync-specs/archive-change. Banshee SHALL hand specification synchronization and change archival to Reaper rather than owning those close-out operations. When a prompt explains how to invoke a workflow, it SHALL name the available `openspec-*` skill and use the syntax supported by the selected backend; it SHALL NOT refer to removed `/opsx:*` command files.

#### Scenario: Spectre plans, Ghost implements
- **WHEN** a change needs to move from idea to implementation
- **THEN** Spectre is the persona whose prompt directs it to explore and propose, while Ghost's prompt directs it to implement an already-proposed change's tasks

#### Scenario: Banshee finds and fixes independently
- **WHEN** Banshee is dispatched to review work across a wider scope than a single task
- **THEN** Banshee's prompt permits explore, propose, update-change, and apply-change, while directing sync-specs and archive-change to Reaper

#### Scenario: Reaper closes the change
- **WHEN** implementation and independent review are complete
- **THEN** Reaper is the persona whose prompt directs it to synchronize approved specs and archive the completed change

#### Scenario: Persona prompt uses supported v2 skill invocation
- **WHEN** an agent follows an OpenSpec invocation example in a persona prompt
- **THEN** the example identifies the relevant `openspec-*` skill and uses `$openspec-*` for Codex or `/openspec-*` for a backend that supports slash skill invocation

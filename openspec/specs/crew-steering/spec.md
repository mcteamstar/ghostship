# Crew Steering Specification

## Purpose

Give every dispatched task the same crew-wide operational context — regardless of which persona runs it or what its prompt says — by exploiting kiro-cli's hardwired steering-doc path, which is loaded for every session no matter the working directory.

## Requirements

### Requirement: Steering docs copied on every launch
The system SHALL copy the steering docs selected by the crew type's manifest (see `crew-manifest`) from the `steering/` Academy pool into the crew container's `~/.kiro/steering/` directory during crew setup, defaulting to every `.md` file when the manifest specifies `"*"`.

#### Scenario: Crew setup copies steering docs
- **WHEN** a crew finishes setup
- **THEN** the crew's `~/.kiro/steering/` directory contains a file for every steering doc name selected by that crew type's manifest, resolved against the transport container's `/steering` Academy pool bind-mount

#### Scenario: kirocrew's manifest yields today's full set
- **WHEN** a crew is stood up using the `kirocrew` crew type, whose manifest specifies `"*"` for steering
- **THEN** every `.md` file present in the transport container's `/steering` Academy pool bind-mount is written into the crew's `~/.kiro/steering/` directory

### Requirement: Steering applies regardless of working directory or persona
The system SHALL rely on kiro-cli loading every file under `~/.kiro/steering/` for every session, independent of the dispatched task's own `subagent_*/` working directory or which persona is running.

#### Scenario: A dispatched task reads steering context
- **WHEN** any persona is dispatched a task in a crew that has steering docs copied in
- **THEN** the content of those docs is part of that task's session context, even though the task itself runs from an isolated per-task working directory unrelated to `~/.kiro/steering/`

### Requirement: Steering content stays environment-scoped, not project-scoped
Steering docs SHALL cover crew-wide environment facts every persona needs regardless of its own prompt (working-directory isolation, the shared OpenSpec store, when to use radio) — not project-specific conventions, which belong in whatever repository the caller delivers into `repo/`.

#### Scenario: Project conventions are not duplicated into steering
- **WHEN** a caller delivers a project repo into the crew workspace
- **THEN** that repo's own conventions are discovered by agents reading the repo directly, not injected via the crew-wide steering docs

### Requirement: Steering warns against unbounded blocking loops
Steering docs SHALL instruct every persona to avoid open-ended blocking polling loops in shell (a loop with no fixed iteration cap and no exit condition reachable from outside the loop), because `steer` cannot interrupt a tool call already in flight and such a loop cannot be redirected once started.

#### Scenario: An agent needs to wait on another agent's output
- **WHEN** a persona's task depends on output that another task may produce later
- **THEN** the steering doc's guidance directs it toward a bounded retry loop with a fixed iteration cap, or radio's send-and-continue pattern — not an unbounded `while true` poll and not `schedule`, since a recurring job can't fire once the crew has idle-stopped between runs

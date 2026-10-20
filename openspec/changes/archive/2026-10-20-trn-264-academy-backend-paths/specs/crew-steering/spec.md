# Spec Delta

## MODIFIED Requirements

### Requirement: Steering docs copied on every launch
The system SHALL copy the steering docs selected by the crew type's manifest (see `crew-manifest`) from the `steering/` Academy pool into the crew container's `~/.agents/context/` staging directory during crew setup, defaulting to every `.md` file when the manifest specifies `"*"`. After staging, `.agents/setup <backend>` delivers the docs to the backend-native path (e.g. `~/.kiro/steering/` for kiro, `~/.claude/rules/` for claude).

#### Scenario: Crew setup copies steering docs (kiro backend)
- **WHEN** a kiro-backend crew finishes setup
- **THEN** the crew's `~/.kiro/steering/` directory contains a file for every steering doc name selected by that crew type's manifest

#### Scenario: Crew setup copies steering docs (claude backend)
- **WHEN** a claude-backend crew finishes setup
- **THEN** the crew's `~/.claude/rules/` directory contains a file for every steering doc name selected by that crew type's manifest

#### Scenario: Crew setup copies steering docs
- **WHEN** a crew finishes setup
- **THEN** the crew's backend-native steering path contains a file for every steering doc name selected by that crew type's manifest, resolved against the transport container's `/steering` Academy pool bind-mount

#### Scenario: kirocrew's manifest yields today's full set
- **WHEN** a crew is stood up using the `kirocrew` crew type, whose manifest specifies `"*"` for steering
- **THEN** every `.md` file present in the transport container's `/steering` Academy pool bind-mount is delivered to the backend-appropriate steering path

### Requirement: Steering applies regardless of working directory or persona
The system SHALL rely on each backend's harness loading every steering/rules file from its native path for every session, independent of the dispatched task's own working directory or which persona is running.

#### Scenario: A dispatched task reads steering context
- **WHEN** any persona is dispatched a task in a crew that has steering docs delivered
- **THEN** the content of those docs is part of that task's session context, regardless of the backend in use

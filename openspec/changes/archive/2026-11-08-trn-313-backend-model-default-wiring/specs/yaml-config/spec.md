# Spec Delta

## ADDED Requirements

### Requirement: Configured model fallbacks reach the agent runtime
A nonempty backend model default SHALL be consumed by the crew runtime when no higher-precedence model applies. A global model default SHALL supply that fallback only when the crew backend has no model default. Resolution SHALL use the crew’s own backend and SHALL preserve dispatch, backend override and applicable persona precedence.

#### Scenario: Backend fallback reaches execution
- **WHEN** a backend has a supported model default and the selected persona has no explicit model
- **THEN** the crew runtime resolves that configured model rather than its harness-selected default

#### Scenario: Backend fallback beats global fallback at runtime
- **WHEN** distinct supported backend and global defaults are configured and no higher-precedence model applies
- **THEN** the crew runtime resolves the backend default

#### Scenario: Global fallback reaches execution
- **WHEN** a supported global default is configured and backend default and higher-precedence models are unset
- **THEN** the crew runtime resolves the global default

#### Scenario: Persona and dispatch retain precedence
- **WHEN** a supported persona pin or dispatch selection applies alongside a different configured fallback
- **THEN** the higher-precedence selection wins in the crew runtime

#### Scenario: Backend override retains precedence
- **WHEN** an explicit persona model is subject to a backend override and no dispatch model is supplied
- **THEN** runtime selection uses the backend override rather than a configured fallback

#### Scenario: Per-crew backend controls fallback
- **WHEN** a crew is launched on a backend different from the transport’s default backend
- **THEN** the model fallback comes from that crew’s backend settings

### Requirement: Empty shipped model defaults preserve harness selection
Shipped backend model defaults and the global model default SHALL remain empty strings. When no model selection applies, Ghostship SHALL leave model selection to the harness without inserting a concrete model. An unavailable selected pin SHALL retain the upstream harness’s rejection/fallback behavior; an empty default SHALL NOT imply task-sensitive automatic routing.

#### Scenario: Out-of-box model delegation
- **WHEN** all model settings and persona selections are unset
- **THEN** Ghostship supplies no concrete model pin and the harness chooses the model

#### Scenario: Rejected pin is distinct from unset selection
- **WHEN** the crew runtime rejects an unavailable selected persona model
- **THEN** documentation identifies the resulting harness-selected default as distinct from a configured Ghostship fallback

### Requirement: Reapplying generated model settings clears obsolete fallback state
Reapplying crew configuration SHALL remove obsolete generated model-fallback state and reflect the current resolved fallback. Clearing a previously configured fallback SHALL restore inheritance without retaining that earlier generated model. Operator YAML and stored credentials SHALL remain unchanged.

#### Scenario: Reapply corrects obsolete generated fallback
- **WHEN** an existing crew has obsolete generated fallback state and configuration is reapplied
- **THEN** the runtime consumes the currently configured fallback and the obsolete state is removed

#### Scenario: Clear configured fallback
- **WHEN** backend and global defaults are cleared after a generated fallback had been applied
- **THEN** the runtime no longer inherits the old generated model and returns to higher-precedence selections or harness selection

### Requirement: Shipped personas inherit backend model configuration
The six shipped persona files SHALL omit explicit model pins. Operator backend overrides SHALL apply to personas with no model or auto, while explicit dispatch selection retains higher priority. Persona prompts and tools SHALL remain unchanged.

#### Scenario: Unpinned shipped persona uses configured fallback
- **WHEN** a supported backend model default is configured and a shipped persona is dispatched without a model argument
- **THEN** the runtime resolves that configured fallback without a foreign persona pin

#### Scenario: Backend override applies to an unpinned persona
- **WHEN** an operator configures a backend model override and a persona has no model or uses auto
- **THEN** that persona uses the backend override unless dispatch explicitly selects a model

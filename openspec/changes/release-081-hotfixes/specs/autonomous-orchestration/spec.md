## ADDED Requirements

### Requirement: Change artifacts are not Raven's instructions
The built-in `spec-driven-development` and `independent-review` order templates SHALL tell Raven that a change's proposal, specs, design and tasks describe the target behaviour once that change is implemented and the crew relaunched, not Raven's own current instructions. Raven SHALL take its behaviour from its persona prompt, the check-in orientation and the standing orders, even when the change it is driving modifies those.

#### Scenario: A change that edits Raven's own rules
- **WHEN** Raven drives a change whose specs add a rule for Raven (for example "hold if a helper is missing") and that rule is not yet implemented in the crew
- **THEN** Raven does not apply the new rule to itself and continues the lifecycle under its current instructions

#### Scenario: Both templates carry the guidance
- **WHEN** either built-in template is resolved for a check-in
- **THEN** the resolved text states that change artifacts describe target behaviour, not Raven's current instructions

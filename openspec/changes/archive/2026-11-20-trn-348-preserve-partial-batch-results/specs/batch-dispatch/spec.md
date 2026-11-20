## ADDED Requirements

### Requirement: Gateway refusal preserves accepted batch members

Batch dispatch SHALL retain and persist prior accepted task IDs when a later spawn is refused by the gateway.

#### Scenario: Gateway refuses a later spawn

- **WHEN** one or more spawns succeed before a later gateway refusal
- **THEN** dispatch returns a partial result with those task IDs and the sanitized failure
- **AND** the registry retains those IDs for pickup without repeating the accepted spawns

#### Scenario: Gateway refuses the first spawn

- **WHEN** the gateway refuses the first spawn
- **THEN** dispatch returns the existing failure response without claiming any accepted members

# Spec Delta

## ADDED Requirements

### Requirement: Gateway health warnings account for crew state

Radar SHALL show stopped crews as stopped without an unreachable gateway warning. It SHALL continue to show a gateway warning for a running crew whose gateway is unhealthy.

#### Scenario: Stopped crew
- **WHEN** a stopped crew reports an unreachable gateway
- **THEN** its row shows stopped without a gateway warning

#### Scenario: Running crew with unhealthy gateway
- **WHEN** a running crew reports an unreachable gateway
- **THEN** its row shows the gateway warning

#### Scenario: Running crew with healthy gateway
- **WHEN** a running crew reports a healthy gateway
- **THEN** its row has no gateway warning

### Requirement: Default fleet ordering

Radar SHALL order crews by creation time, newest first, within each running and inactive section by default. Crews without a valid creation time SHALL appear after those with valid creation times. The Last Task sort control SHALL continue to work.

#### Scenario: Multiple crews in a section
- **WHEN** the fleet table has no Last Task sort selected
- **THEN** each section shows the most recently created crews first

#### Scenario: Last Task sort selected
- **WHEN** the user selects the Last Task sort
- **THEN** the selected Last Task ordering applies within each section

## ADDED Requirements

### Requirement: Crew uploads enforce resource budgets

Supply SHALL limit actual request bytes for all upload modes and bound archive output bytes and member count. Bundle processing SHALL enforce an output storage budget. Limits SHALL be configurable.

#### Scenario: Upload exceeds its request budget
- **WHEN** the declared or actual request size exceeds the configured limit
- **THEN** Transport returns HTTP 413 and clears partial staging

#### Scenario: Unpack or checkout exceeds its budget
- **WHEN** an archive or bundle exceeds its processing limits
- **THEN** Transport returns HTTP 413, clears partial staging, and preserves the existing destination

#### Scenario: Upload fits its budgets
- **WHEN** an authorized plain upload, unpack, or bundle checkout fits its budgets
- **THEN** it retains existing supply behavior

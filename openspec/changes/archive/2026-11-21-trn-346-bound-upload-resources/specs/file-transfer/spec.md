## ADDED Requirements

### Requirement: Crew uploads enforce resource budgets

Supply SHALL enforce configurable request byte limits for all upload modes, archive output byte and member limits, and a storage limit during bundle processing that includes Git metadata and checkout files. Request staging and handoff SHALL use bounded memory.

#### Scenario: Upload exceeds its request budget
- **WHEN** the declared or actual request size exceeds the configured limit
- **THEN** Transport returns HTTP 413 and clears partial staging

#### Scenario: Unpack or checkout exceeds its budget
- **WHEN** an archive or bundle exceeds its processing limits
- **THEN** Transport returns HTTP 413, clears partial staging, and preserves the existing destination

#### Scenario: Client disconnects during request staging
- **WHEN** the client disconnects before the full request is staged
- **THEN** Transport removes partial staging and leaves the destination untouched

#### Scenario: Upload fits its budgets
- **WHEN** an authorized plain upload, unpack, or bundle checkout fits its budgets
- **THEN** it retains existing supply behavior

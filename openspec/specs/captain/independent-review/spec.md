# captain/independent-review Specification

## Purpose

Defines the `independent-review` built-in captain template — its four-reviewer dispatch pattern, individual report contracts, optional change-scoping behavior, and the Raven-driven consolidation step that produces a single findings document for the Admiral.

## Requirements

### Requirement: independent-review template dispatches four concurrent, isolated reviewers

When the captain `independent-review` template is ordered, the system SHALL dispatch four review agents concurrently. Each reviewer SHALL work directly from the codebase with no knowledge of the other reviewers' tasks or findings. The four reviewers are:

1. **Docs completeness (Wraith)** — verifies documentation accuracy against the codebase: stale references, missing or incorrect env var documentation, README drift.
2. **Security review (Banshee)** — examines the threat model, known vulnerability classes, secret handling patterns, and injection surfaces.
3. **Code quality (Banshee)** — identifies race conditions, error handling gaps, and edge cases in recent or targeted code.
4. **Test coverage (Banshee)** — identifies unit test gaps, missing scenarios, and e2e coverage gaps.

#### Scenario: Four reviewers are dispatched without knowledge of each other

- **WHEN** `captain(crew_id=<id>, action="order", template="independent-review")` is sent
- **THEN** Raven dispatches all four reviewer agents and the task description for each reviewer SHALL NOT include the findings scope or task of any other reviewer

#### Scenario: Each reviewer submits a standalone report to raven@localhost

- **WHEN** a reviewer completes its analysis
- **THEN** it SHALL mail its findings as a standalone report to `raven@localhost` before its task ends, and the report SHALL be self-contained (readable without the other reviewers' reports)

#### Scenario: Raven waits for all four reports before consolidating

- **WHEN** Raven receives a reviewer's report
- **THEN** Raven SHALL NOT send the consolidated findings to the Admiral until reports from all four reviewers have been received

### Requirement: independent-review consolidates findings and mails admiral@localhost

After receiving all four reviewer reports, Raven SHALL produce a single consolidated findings document and send it to `admiral@localhost`. The consolidated document SHALL:

- Group findings by severity (Critical, High, Medium, Low, Informational)
- Cross-reference findings flagged by more than one reviewer
- Include recommended next actions for each finding group

#### Scenario: Consolidated report sent after all four reports arrive

- **WHEN** Raven has received reports from all four reviewers
- **THEN** Raven SHALL mail a consolidated findings document to `admiral@localhost` that groups findings by severity, identifies cross-reviewer findings, and lists recommended next actions

#### Scenario: No findings produces a clean-bill report

- **WHEN** all four reviewers report no findings of substance
- **THEN** Raven SHALL still send a consolidated document to `admiral@localhost` summarizing the clean state across all four review tracks

### Requirement: independent-review accepts an optional change_name to scope the review

The `independent-review` template SHALL accept an optional `change_name` parameter. When `change_name` is provided, each reviewer SHALL scope its analysis to the code changes associated with that named change (e.g., recent commits, the change's tasks.md, its affected files). Without `change_name`, reviewers SHALL review the whole codebase.

#### Scenario: Review scoped to a named change

- **WHEN** `captain(crew_id=<id>, action="order", template="independent-review", change_name="trn-107")` is sent
- **THEN** each reviewer's dispatch context SHALL include the change name and instruct the reviewer to focus on code and artifacts associated with that change

#### Scenario: Review covers the whole codebase when no change_name is given

- **WHEN** `captain(crew_id=<id>, action="order", template="independent-review")` is sent with no `change_name`
- **THEN** each reviewer's dispatch context SHALL instruct it to review the whole codebase with no change-specific scope restriction

#### Scenario: change_name must be valid kebab-case

- **WHEN** `captain(crew_id=<id>, action="order", template="independent-review", change_name="TRN 107")` is sent with an invalid change name (contains space or uppercase)
- **THEN** the captain tool SHALL return an error and dispatch no reviewers

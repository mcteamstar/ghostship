# Spec Delta

## MODIFIED Requirements

### Requirement: independent-review template dispatches four concurrent, isolated reviewers

When the captain `independent-review` template is ordered, the system SHALL dispatch seven review agents concurrently (1 Wraith + 6 Banshees). Each reviewer SHALL work directly from the codebase with no knowledge of the other reviewers' tasks or findings. The seven reviewers are:

1. **Docs completeness (Wraith)** — verifies documentation accuracy against the codebase: stale references, missing or incorrect env var documentation, README drift.
2. **Security review (Banshee)** — examines the threat model, known vulnerability classes, secret handling patterns, and injection surfaces.
3. **Code quality (Banshee)** — identifies race conditions, error handling gaps, and edge cases in recent or targeted code.
4. **Test coverage Shard A (Banshee)** — identifies unit test gaps, missing scenarios, and e2e coverage gaps in `transport/`.
5. **Test coverage Shard B (Banshee)** — identifies unit test gaps, missing scenarios, and e2e coverage gaps in `tests/unit/`.
6. **Test coverage Shard C (Banshee)** — identifies unit test gaps, missing scenarios, and e2e coverage gaps in `tests/integration/` and all other paths.
7. **Privacy review (Banshee)** — scans source code, docs, and openspec artifacts for internal infrastructure references that should not appear in a public repository: hostnames, IP addresses, VM/service names, internal ticket identifiers, real file paths, real names or email addresses, and internal URLs.

#### Scenario: Four reviewers are dispatched without knowledge of each other

- **WHEN** `captain(crew_id=<id>, action="order", template="independent-review")` is sent
- **THEN** Raven dispatches all seven reviewer agents and the task description for each reviewer SHALL NOT include the findings scope or task of any other reviewer

#### Scenario: Five reviewers are dispatched without knowledge of each other

- **WHEN** `captain(crew_id=<id>, action="order", template="independent-review")` is sent
- **THEN** Raven dispatches all seven reviewer agents and the task description for each reviewer SHALL NOT include the findings scope or task of any other reviewer

#### Scenario: Each reviewer submits a standalone report to raven@localhost

- **WHEN** a reviewer completes its analysis
- **THEN** it SHALL mail its findings as a standalone report to `raven@localhost` before its task ends, and the report SHALL be self-contained (readable without the other reviewers' reports)

#### Scenario: Raven waits for all four reports before consolidating

- **WHEN** Raven receives a reviewer's report
- **THEN** Raven SHALL NOT send the consolidated findings to the Admiral until reports from all seven reviewers have been received

#### Scenario: Raven waits for all five reports before consolidating

- **WHEN** Raven receives a reviewer's report
- **THEN** Raven SHALL NOT send the consolidated findings to the Admiral until reports from all seven reviewers (docs, security, quality, test-coverage-a, test-coverage-b, test-coverage-c, privacy) have been received

## MODIFIED Requirements

### Requirement: independent-review consolidates findings and mails admiral@localhost

After receiving all seven reviewer reports, Raven SHALL produce a single consolidated findings document and send it to `admiral@localhost`. The consolidated document SHALL:

- Group findings by severity (Critical, High, Medium, Low, Informational)
- Cross-reference findings flagged by more than one reviewer
- Include a **Test Coverage** section merging the three shard sub-reports (Shard A: `transport/`, Shard B: `tests/unit/`, Shard C: `tests/integration/` + other), with each finding attributed to its shard
- Include a **Privacy** section for privacy probe findings
- Include recommended next actions for each finding group

#### Scenario: Consolidated report sent after all four reports arrive

- **WHEN** Raven has received reports from all seven reviewers
- **THEN** Raven SHALL mail a consolidated findings document to `admiral@localhost` that groups findings by severity, identifies cross-reviewer findings, includes a Test Coverage section with shard attribution, includes a Privacy section, and lists recommended next actions

#### Scenario: Consolidated report sent after all five reports arrive

- **WHEN** Raven has received reports from all seven reviewers
- **THEN** Raven SHALL mail a consolidated findings document to `admiral@localhost` that groups findings by severity, identifies cross-reviewer findings, includes a Test Coverage section with shard attribution, includes a Privacy section, and lists recommended next actions

#### Scenario: No findings produces a clean-bill report

- **WHEN** all seven reviewers report no findings of substance
- **THEN** Raven SHALL still send a consolidated document to `admiral@localhost` summarizing the clean state across all seven review tracks

## ADDED Requirements

### Requirement: independent-review fans out test-coverage review across multiple parallel Banshees

The test-coverage review SHALL be split across N parallel Banshee tasks (default
N=3, configurable) rather than a single task, to reduce wall-clock time. Each
Banshee is assigned a disjoint subset of the codebase (e.g. by module or
directory). Raven SHALL collect all N test-coverage sub-reports before
incorporating them into the consolidated report as a single merged test-coverage
section.

#### Scenario: Test-coverage Banshees dispatched in parallel

- **WHEN** the `independent-review` template fires
- **THEN** Raven SHALL dispatch N test-coverage Banshees concurrently, each with a distinct task prefix `REVIEW test-coverage-<shard> <intent_id> <change?>` identifying its assigned shard

#### Scenario: Raven waits for all test-coverage shards before consolidating

- **WHEN** Raven is collecting reviewer reports
- **THEN** it SHALL wait for all N test-coverage sub-reports (subjects `review test-coverage-<shard> done <change?>`) in addition to the docs, security, quality, and privacy reports before sending the consolidated findings

#### Scenario: Test-coverage shards merged into one section in consolidated report

- **WHEN** all N test-coverage sub-reports arrive
- **THEN** the consolidated report SHALL contain a single merged **Test Coverage** section combining findings from all shards, with each finding attributed to its shard for traceability

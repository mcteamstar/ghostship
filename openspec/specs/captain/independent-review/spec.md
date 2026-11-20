# Spec Delta

## Purpose

The `independent-review` Captain template dispatches isolated reviewers, collects their reports, and sends a consolidated findings report to the Admiral.

## Requirements

### Requirement: independent-review covers five tracks across seven tasks

The `independent-review` order SHALL cover five review tracks: docs completeness (Wraith), security, code quality, test coverage, and privacy (Banshees). It SHALL dispatch seven isolated tasks concurrently: docs, security, quality, coverage shards A/B/C, and privacy. Each task SHALL review code without receiving other tasks' scopes or findings.

#### Scenario: Five tracks dispatch seven isolated tasks

- **WHEN** `captain(crew_id=<id>, action="order", template="independent-review")` is sent
- **THEN** Raven dispatches one Wraith docs task and six Banshee tasks: security, quality, coverage shards A/B/C, and privacy

#### Scenario: Each review task receives only its assigned scope

- **WHEN** Raven dispatches any of the seven tasks
- **THEN** its task description identifies only that task's review scope and excludes other tasks' scopes and findings

#### Scenario: Each review task submits a standalone report to raven@localhost

- **WHEN** a reviewer completes its analysis
- **THEN** it mails a self-contained standalone report to `raven@localhost` before its task ends

#### Scenario: Raven waits for all seven task reports before consolidating

- **WHEN** Raven receives a review report
- **THEN** Raven waits for reports from docs, security, quality, coverage shards A/B/C, and privacy before sending the consolidated findings to the Admiral

### Requirement: independent-review consolidates findings and mails admiral@localhost

After receiving all seven task reports, Raven SHALL produce one consolidated findings document for `admiral@localhost`. It SHALL group findings by Critical, High, Medium, Low, and Informational severity; cross-reference overlapping findings; attribute coverage findings to their shard in a Test Coverage section; group privacy findings by the seven scan categories in a Privacy section; and recommend next actions for each finding group.

#### Scenario: Consolidated report sent after all seven task reports arrive

- **WHEN** Raven has received reports from all seven tasks
- **THEN** Raven mails `admiral@localhost` a consolidated document with severity groups, cross-review references, shard-attributed Test Coverage findings, a Privacy section, and recommended next actions

#### Scenario: No findings produces a clean summary across five tracks

- **WHEN** all seven tasks report no findings of substance
- **THEN** Raven sends `admiral@localhost` a consolidated document summarizing the clean state across all five tracks and all three coverage shards

### Requirement: independent-review uses three fixed test-coverage shards

The test-coverage track SHALL dispatch exactly three parallel Banshee tasks, one for each fixed shard: A (`transport/`), B (`tests/unit/`), and C (`tests/integration/` plus all other paths). Raven SHALL collect all three shard reports before merging them into the consolidated Test Coverage section. The shard count is fixed; configurable fan-out is deferred to TRN-344.

#### Scenario: Three fixed test-coverage shards dispatch in parallel

- **WHEN** the `independent-review` template fires
- **THEN** Raven dispatches exactly three concurrent test-coverage Banshees with prefixes `REVIEW test-coverage-a`, `REVIEW test-coverage-b`, and `REVIEW test-coverage-c`, one per shard

#### Scenario: Raven waits for all three fixed coverage shards

- **WHEN** Raven collects reviewer reports
- **THEN** it waits for all three `review test-coverage-<shard> done <change?>` reports in addition to the docs, security, quality, and privacy reports before sending the consolidated findings

#### Scenario: Coverage findings retain shard attribution

- **WHEN** all three test-coverage reports arrive
- **THEN** the consolidated report contains one merged Test Coverage section with each finding attributed to shard A, B, or C

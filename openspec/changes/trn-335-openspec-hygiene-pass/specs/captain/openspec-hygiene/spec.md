# Spec Delta

## Purpose

Provides a manually invoked, read-only Captain workflow for assessing OpenSpec validity, lifecycle hygiene, and coherence with a repository's implementation and documentation.

## ADDED Requirements

### Requirement: Hygiene pass resolves the target repository's OpenSpec scope
The hygiene pass SHALL inspect either the whole target repository or an explicitly selected set of changes, using only that repository's resolved OpenSpec root or store.

#### Scenario: Whole-repository pass
- **WHEN** the Admiral orders a hygiene pass without selecting changes
- **THEN** the workflow inspects all changes and specs in the target repository's resolved OpenSpec root

#### Scenario: Selected-change pass
- **WHEN** the Admiral orders a hygiene pass with one or more change names
- **THEN** the workflow scopes change-specific checks to those changes and their related main specs

#### Scenario: Target has no resolvable OpenSpec root
- **WHEN** the target repository has no OpenSpec root or its declared store cannot be resolved
- **THEN** the workflow reports the blocker and SHALL NOT initialize a store, register a store, or fall back to another repository's store

### Requirement: Hygiene pass checks OpenSpec validity and lifecycle state
The workflow SHALL run strict OpenSpec validation for its selected scope and inspect change status, artifacts, and task progress to identify incomplete, stale, or potentially archive-ready work.

#### Scenario: Strict validation finds errors
- **WHEN** strict validation reports an error for the selected scope
- **THEN** the report includes the affected change or spec, validation evidence, and a recommended remediation

#### Scenario: Change appears ready for verification or archive
- **WHEN** a selected change has complete planning artifacts and all tracked tasks marked complete
- **THEN** the report labels it as a candidate for verification or archive and does not claim it has been verified or archived

#### Scenario: Open changes appear stale or out of date
- **WHEN** status or artifact evidence indicates an incomplete, stale, or superseded change
- **THEN** the report identifies the evidence and recommends a follow-up without changing the change state

### Requirement: Hygiene pass verifies apparent completion candidates
For a selected change that appears ready for verification from its artifact and task status, the workflow SHALL invoke the bundled `openspec-verify-change` skill and include its advisory result without syncing specs or archiving the change.

#### Scenario: Candidate change receives verification
- **WHEN** a selected change has complete planning artifacts and all tracked tasks marked complete
- **THEN** the hygiene report includes the verifier's findings and treats them as advisory evidence rather than archive approval

#### Scenario: Verifier skill is unavailable
- **WHEN** the verifier skill cannot be discovered or run for an apparent completion candidate
- **THEN** the report marks verification as not performed, identifies the missing skill evidence, and makes no clean or verified claim

### Requirement: Hygiene pass cross-checks specs, implementation, and documentation
The workflow SHALL use independent, read-only review tasks to find contradictions between OpenSpec artifacts, likely spec-related implementation issues, and documentation drift from the behavior described by the specs and code.

#### Scenario: Contradiction or likely spec-related code issue is found
- **WHEN** a reviewer finds conflicting requirements or code that appears inconsistent with an applicable requirement
- **THEN** its report identifies the conflicting or affected artifacts and explains the evidence without expanding into general code-quality or security review

#### Scenario: Documentation is inconsistent with the specified behavior
- **WHEN** repository documentation describes behavior that conflicts with the OpenSpec requirements or relevant implementation
- **THEN** its report identifies the documentation and source paths and recommends a correction

### Requirement: Hygiene findings are evidence-based and non-mutating
The workflow SHALL send a consolidated report to the Admiral with status evidence, affected paths, confidence, and recommended remediation, while leaving repository files and OpenSpec state unchanged.

#### Scenario: Findings are consolidated after reviewers finish
- **WHEN** all validation and review tasks for a pass are complete
- **THEN** Raven sends one report that distinguishes confirmed validation failures from reviewer assessments and recommendations

#### Scenario: Required evidence is unavailable
- **WHEN** a validation or review check cannot access evidence required to assess a requirement
- **THEN** the report marks that check as not verified, identifies the missing evidence, and makes no clean or verified claim for it

#### Scenario: Hygiene pass completes
- **WHEN** the report has been delivered
- **THEN** the manually ordered workflow ends and SHALL NOT sync specs, archive changes, edit files, schedule recurring runs, or access deployed environments

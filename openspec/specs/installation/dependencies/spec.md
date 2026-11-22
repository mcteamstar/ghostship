# dependency-management Specification

## Purpose

Governs how transport Python dependencies are selected, pinned, and upgraded — covering provenance requirements, pinning strategy, and the boundary between runtime and dev-only dependencies.

## Requirements

### Requirement: Dependency provenance policy

Transport runtime dependencies SHALL be owned by an organisation or well-established project rather than a single individual maintainer. Individual-maintainer packages MAY be used as dev/test-only dependencies where blast radius is limited to the development workflow.

#### Scenario: Runtime dep fails provenance check
- **WHEN** a new runtime dependency is proposed whose PyPI owner is a single individual with no organisational backing
- **THEN** an alternative with organisational backing SHALL be evaluated before accepting it

#### Scenario: Dev-only dep relaxed policy
- **WHEN** a dependency is used only in the test runner or CI and is not installed in the transport container
- **THEN** the single-maintainer restriction does not apply, though well-maintained alternatives are preferred

### Requirement: Pin strategy

Runtime dependencies SHALL be pinned to an exact version (`==`) or a tight range (`>=x,<y` spanning no more than one major version). Unpinned or open-ended ranges SHALL NOT be used for runtime deps.

#### Scenario: Exact pin for security-critical deps
- **WHEN** a dependency handles cryptography, authentication, or network protocol parsing
- **THEN** it SHALL be pinned to an exact version or a tight range with an explicit upper bound

#### Scenario: Range for framework deps
- **WHEN** a dependency is a foundational framework (starlette, uvicorn) where the transport must accept compatible minor updates
- **THEN** a `>=x,<y` range spanning one major version is acceptable

### Requirement: Compat shim prohibition

Dependencies kept solely to satisfy the transitive requirements of another dependency SHALL be removed when that dependency is replaced. A comment explaining the shim's purpose SHALL be present for any remaining compatibility pin.

#### Scenario: Shim removal on upstream change
- **WHEN** the dependency that required a compat shim is replaced or updated to no longer need it
- **THEN** the shim dependency SHALL be removed from `requirements.txt` in the same change

### Requirement: Discoverable dependency inventory

Ghostship SHALL maintain a repository-linked inventory of externally supplied runtime, build and development components, identifying authoritative declarations, version policy, upstream source, maintainer owner, review date, compatibility constraints and verification evidence. Bundled components SHALL identify their supplying dependency.

#### Scenario: Maintainer investigates a bundled CLI
- **WHEN** a maintainer consults the inventory for Codex or Kiro CLI
- **THEN** it identifies the adapter or base image supplying the CLI and distinguishes declared constraints from verified installed versions

#### Scenario: Inventory completeness check
- **WHEN** a dependency declaration changes or a tracked input is missing from the inventory
- **THEN** the manually invoked check reports the stale or missing entry and fails rather than accepting silent drift

### Requirement: Manual dependency checks

Ghostship SHALL provide a manually invoked, read-only dependency check command showing declared versions, upstream candidates, compatibility evidence, overdue reviews and lookup failures. Checks SHALL run only on explicit invocation, without scheduled jobs or automated report publishing, and SHALL NOT mutate dependency pins, running crews or deployments.

#### Scenario: Maintainer runs a check
- **WHEN** a maintainer invokes the documented local command
- **THEN** it prints candidates, compatibility status and recorded compatibility evidence, and review status for tracked components without scheduling future checks or publishing reports

#### Scenario: Successful lookup has no matching candidate
- **WHEN** an upstream lookup succeeds but returns no candidate matching the configured stable or prerelease policy
- **THEN** the component is reported as having no matching candidate, distinct from a failed lookup, and the command remains complete unless another lookup failed or was truncated

#### Scenario: Registry lookup fails
- **WHEN** an upstream source cannot be queried
- **THEN** the affected component is marked unknown or failed, other results remain available, and the command exits with an incomplete status rather than declaring everything current

### Requirement: Maintainer review cadence

Maintainers SHALL review tracked dependencies monthly and before releases, record dated outcomes and deferral reasons, and flag reviews older than 30 days. Known security advisories and upstream compatibility warnings SHALL trigger earlier assessment.

#### Scenario: Available update is deferred
- **WHEN** a maintainer decides to retain an older supported version
- **THEN** the inventory records the review date, reason, evidence and next review rather than implying the dependency was overlooked

### Requirement: Compatible upgrade verification

Dependency upgrades SHALL preserve existing provenance and pinning policies, validate coupled components together, and record build and affected integration evidence before release. Available upstream versions SHALL NOT be described as compatible without supporting evidence. Deployment SHALL require explicit approval.

#### Scenario: ACP adapter upgrade
- **WHEN** an adapter or supplied CLI is upgraded
- **THEN** verification covers KiroCrew support, authentication compatibility, model discovery and a fresh-crew turn with the actual selected model recorded

#### Scenario: Build or framework dependency upgrade
- **WHEN** KiroCrew, OpenSpec, Node.js or Python dependencies change
- **THEN** review records the applicable migration, skill compatibility, checksum or affected-test checks and confirms the built resolution instead of treating the declaration alone as installed proof

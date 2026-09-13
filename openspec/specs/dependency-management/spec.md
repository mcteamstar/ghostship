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

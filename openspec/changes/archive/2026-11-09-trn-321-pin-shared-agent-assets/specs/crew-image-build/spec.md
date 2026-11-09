# Spec Delta

> Historical delta: superseded by commit `9ca4735e`; the main `crew-image-build` spec records the accepted `main` default and resolved-commit behavior.

## ADDED Requirements

### Requirement: Shared agent assets are pinned to an immutable commit

The crew image SHALL build shared agent assets from an immutable commit by default, and SHALL record the commit it built from. A moving branch SHALL only be used when an operator configures one explicitly, and the installer SHALL warn when it is.

#### Scenario: Default build
- **WHEN** an operator builds the crew image without overriding the shared agent assets ref
- **THEN** the assets are fetched at the pinned commit and the image label records that full commit SHA

#### Scenario: Upstream main changes
- **WHEN** a new commit lands on the shared agent assets repository's default branch
- **THEN** a default rebuild of the crew image still contains the previously pinned assets

#### Scenario: Operator configures a branch
- **WHEN** an operator sets the shared agent assets ref to a branch name
- **THEN** the build succeeds using that branch, the installer prints a warning that the ref is mutable, and the image label records the resolved commit SHA

#### Scenario: Inventory check on a moving ref
- **WHEN** the dependency check runs against a repository whose default shared agent assets ref is not a commit SHA
- **THEN** it reports the shared agent assets entry as unpinned

# Spec Delta

## ADDED Requirements

### Requirement: Skills upgrade flow is documented in operator-facing docs

The project SHALL provide operator-facing documentation that explains the `ghostship upgrade --skills` workflow: when it is needed (after pulling a new ghostship version that ships updated academy skills), what it does (rebuild images → restart transport → run `ghostship setup`), how to verify that skill symlinks are current after an upgrade, and how to run each step manually when the combined flag is unavailable.

#### Scenario: Operator knows when to use --skills

- **WHEN** an operator reads the upgrade documentation
- **THEN** they can determine whether `ghostship upgrade` alone or `ghostship upgrade --skills` is the correct command after pulling a new version that includes skill updates

#### Scenario: Operator can verify skill symlinks are current

- **WHEN** an operator follows the upgrade documentation
- **THEN** they find at least one verification step (e.g. checking the symlink target or running `ghostship setup --agent <harness>`) that confirms skill symlinks point to the new version

#### Scenario: Manual fallback steps are documented

- **WHEN** `ghostship upgrade --skills` is unavailable or the combined command fails mid-way
- **THEN** the documentation lists the equivalent manual steps (`ghostship upgrade` then `ghostship setup`) so the operator can recover without reading source code


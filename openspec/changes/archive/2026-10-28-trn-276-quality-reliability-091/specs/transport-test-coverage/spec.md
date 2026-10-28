## MODIFIED Requirements

### Requirement: pytest-cov is run in CI

The CI test invocation SHALL include `--cov=transport` (or equivalent) so that
coverage gaps surface automatically on every pull request rather than requiring
manual inspection.

#### Scenario: CI pytest invocation includes coverage reporting
- **WHEN** the CI test workflow runs
- **THEN** a coverage report for `transport/` is generated
- **THEN** coverage gaps are visible in the PR output

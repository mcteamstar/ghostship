## Purpose

Gives the project one discoverable home and one entry point for every test suite — unit, integration, and E2E — so "run the tests" is a single command instead of knowing where each suite lives and how to invoke it.

## ADDED Requirements

### Requirement: Single test root
All test suites SHALL live under the repository-root `tests/` directory. No test files SHALL live outside `tests/` in application source directories (e.g. `transport/`) once this change completes.

#### Scenario: Python unit tests relocated
- **WHEN** a contributor looks for the transport server's test suite
- **THEN** they find it under `tests/` (not `transport/`), organized by the layout chosen in this change's `design.md`

#### Scenario: New test added
- **WHEN** a contributor adds a new test for any part of the system
- **THEN** the correct location is unambiguous from the existing `tests/` layout — no new top-level test location is needed

### Requirement: Suite categories
Tests SHALL be organized into at least three categories: unit (no external dependencies — Podman, network, a live install — required), integration (requires a real Podman socket/runtime but not a full ghostship install), and E2E (requires an actual running `ga-transport` and exercises real MCP-tool-level flows like `launch` → `dispatch` → `pickup`). Each category SHALL be independently selectable when running the orchestrator.

#### Scenario: Unit suite runs without Podman
- **WHEN** the unit suite is run in an environment with no Podman binary or socket
- **THEN** all unit tests execute and pass (Podman-dependent test classes/methods remain self-skipping via their existing `skipUnless` guards, as they do today)

#### Scenario: E2E suite is a first-class, if initially small, category
- **WHEN** the orchestrator is asked to run the E2E suite
- **THEN** it runs whatever E2E tests exist under that category (even zero or one today) without special-casing — adding a new E2E test requires no orchestrator changes

### Requirement: Single orchestrator entry point
A single script at the root of `tests/` SHALL run any combination of suite categories, produce one aggregate pass/fail summary across all suites run, and exit non-zero if any suite reports a failure.

#### Scenario: Run everything
- **WHEN** the orchestrator is invoked with no arguments (or an explicit "all" selection)
- **THEN** unit, integration, and E2E suites all run, and the final summary reports totals across all of them

#### Scenario: Run a single category
- **WHEN** the orchestrator is invoked asking for only the unit category
- **THEN** only unit tests run; integration and E2E suites are not invoked

#### Scenario: Any suite failure fails the run
- **WHEN** any invoked suite reports one or more failures
- **THEN** the orchestrator's own exit code is non-zero, regardless of how many other suites passed

### Requirement: CI runs the orchestrator
`.github/workflows/test.yml` SHALL invoke the orchestrator rather than calling a suite-specific command directly, selecting whichever suite categories are safe to run in the CI environment.

#### Scenario: CI invocation
- **WHEN** the `tests` GitHub Actions workflow runs
- **THEN** it calls the `tests/` orchestrator (not a raw `python -m unittest` or suite-specific command) with the category selection appropriate for `ubuntu-latest`

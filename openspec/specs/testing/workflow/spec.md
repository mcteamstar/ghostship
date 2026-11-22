# testing/workflow Specification

## Purpose

Defines verification coverage for workflow behavior.

## Requirements

### Requirement: Test suite runs safely inside crew containers

The test suite SHALL separate pure unit tests from Podman-dependent tests, which skip unless Podman is available. Tests relocated under `tests/` SHALL document which classes require Podman and retain a working package/flat import shim.

#### Scenario: Full suite completes inside a crew container
- **WHEN** the relocated test suite's unit-category tests are run inside a crew container where Podman is absent
- **THEN** Podman-dependent tests are skipped, all other tests run and pass, and the suite exits 0

#### Scenario: Full suite runs all tests on a host with Podman
- **WHEN** the relocated test suite's unit and integration categories are run on a host where Podman is available
- **THEN** all tests including Podman-dependent ones are executed

#### Scenario: Server module still importable after relocation
- **WHEN** the relocated test suite imports the transport server module
- **THEN** exactly one of the two existing import strategies (package-style `transport.server`, or the flat fallback) resolves correctly and deterministically from the new location — not by accident of which directory happens to be on `sys.path` for a given invocation

### Requirement: e2e suite fixture model

Each e2e file SHALL launch one module-level `SHARED_CREW_ID` crew in `setUpModule` and nuke it in `tearDownModule`. Stateless classes SHALL reuse it and SHALL NOT launch or nuke per class.

#### Scenario: Module-level crew is launched once per file
- **WHEN** the e2e test runner imports a test file
- **THEN** exactly one `setUpModule` launch call is made for that file, shared by all stateless test classes within it

#### Scenario: Module-level crew is torn down after all tests in the file complete
- **WHEN** all tests in a test file have run
- **THEN** `tearDownModule` nukes the shared crew exactly once

#### Scenario: Stateless test classes use the shared crew
- **WHEN** `TestDispatchPickup`, `TestSupplyEvac`, `TestScheduleTool`, `TestResponseSchemas`, or the stateless `TestErrorPaths` tests run
- **THEN** they operate against the module-level shared crew and do not launch or nuke any crew of their own

#### Scenario: TestSteerTool uses its own crew
- **WHEN** `TestSteerTool.setUpClass` runs
- **THEN** a dedicated crew named `e2e-steer` is launched; `tearDownClass` nukes it

#### Scenario: TestCrewLifecycle uses its own crew
- **WHEN** `TestCrewLifecycle.test_launch_and_nuke` runs
- **THEN** it launches and nukes a dedicated `e2e-lifecycle` crew independently of the shared crew

#### Scenario: TestCaptainStatusStoppedCrew uses its own crew
- **WHEN** `TestCaptainStatusStoppedCrew.setUpClass` runs
- **THEN** a dedicated crew is launched and stopped via Podman; `tearDownClass` nukes it

#### Scenario: TestErrorPaths lifecycle tests use throw-away crews
- **WHEN** `test_pickup_nonexistent_task`, `test_launch_duplicate_crew`, or `test_nuke_without_confirm` runs
- **THEN** each test launches and nukes its own short-lived throw-away crew within the test method body, using a distinct `crew_id` that does not collide with `SHARED_CREW_ID`

### Requirement: pytest-cov is run in CI

The CI test invocation SHALL include `--cov=transport` (or equivalent) so that
coverage gaps surface automatically on every pull request rather than requiring
manual inspection.

#### Scenario: CI pytest invocation includes coverage reporting
- **WHEN** the CI test workflow runs
- **THEN** a coverage report for `transport/` is generated
- **THEN** coverage gaps are visible in the PR output

### Requirement: Critical transport modules have direct unit test coverage

Direct unit tests SHALL cover `transport/security.py`, file HMACs, policy injection/raw transfer, and OpenAPI generation in their `tests/unit` modules. Each SHALL exercise exported functions or security paths and name a guarded failure mode.

#### Scenario: test_security.py exists and passes
- **WHEN** `pytest tests/unit/test_security.py` is run
- **THEN** all tests pass with no errors

#### Scenario: test_files.py exists and passes
- **WHEN** `pytest tests/unit/test_files.py` is run
- **THEN** all tests pass with no errors

#### Scenario: test_openapi.py exists and passes
- **WHEN** `pytest tests/unit/test_openapi.py` is run
- **THEN** all tests pass with no errors

#### Scenario: files.py path-traversal is rejected
- **WHEN** `_safe_workspace_path` is called with a path such as `../../etc/passwd` that resolves outside the workspace root
- **THEN** the path is rejected without accessing the filesystem

#### Scenario: files.py HMAC token expiry is rejected
- **WHEN** an upload request carries an expired HMAC token
- **THEN** the upload is rejected with an appropriate error response

#### Scenario: files.py HMAC mode-mismatch is rejected
- **WHEN** an upload request carries a valid HMAC token but for a different operation mode
- **THEN** the upload is rejected

#### Scenario: files.py git-bundle clone fallback is exercised
- **WHEN** `_transfer_upload` is called and the direct upload fails
- **THEN** the git-bundle clone fallback path is attempted

### Requirement: Python integration suites run through the supported test workflow
The supported test workflow SHALL execute the repository's Python integration suites, including profile launch flow, on-demand recovery, model defaults, and Codex sandbox coverage. Tests requiring a built crew image or Podman connection MAY run in a dedicated Podman-backed CI job, but SHALL be included in the documented release verification workflow and SHALL report failures as CI failures.

#### Scenario: Lightweight Python integration tests run in CI
- **WHEN** CI runs the integration test category
- **THEN** the profile launch-flow and on-demand recovery Python suites run with their declared Python dependencies

#### Scenario: Crew-image integration tests run in Podman-backed CI
- **WHEN** CI runs the Podman-backed integration category
- **THEN** it builds or selects the required crew image and runs the model-default and Codex-sandbox suites against a disposable container
- **THEN** failures in those suites fail the CI job

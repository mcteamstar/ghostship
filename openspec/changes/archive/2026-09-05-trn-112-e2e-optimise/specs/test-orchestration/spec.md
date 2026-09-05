## MODIFIED Requirements

### Requirement: Single orchestrator entry point
A single script at the root of `tests/` SHALL run any combination of suite categories, produce one aggregate pass/fail summary across all suites run, and exit non-zero if any suite reports a failure. When running the E2E suite, the orchestrator SHALL use a parallel test-class runner (`unittest-parallel`) when available in the active Python environment, and SHALL fall back to the standard serial `python -m unittest discover` when the package is absent.

#### Scenario: Run everything
- **WHEN** the orchestrator is invoked with no arguments (or an explicit "all" selection)
- **THEN** unit, integration, and E2E suites all run, and the final summary reports totals across all of them

#### Scenario: Run a single category
- **WHEN** the orchestrator is invoked asking for only the unit category
- **THEN** only unit tests run; integration and E2E suites are not invoked

#### Scenario: Any suite failure fails the run
- **WHEN** any invoked suite reports one or more failures
- **THEN** the orchestrator's own exit code is non-zero, regardless of how many other suites passed

#### Scenario: E2E suite runs in parallel when unittest-parallel is available
- **WHEN** the orchestrator is asked to run the E2E suite AND `unittest-parallel` is importable in the active Python environment
- **THEN** the orchestrator invokes `python -m unittest_parallel` (or equivalent) to dispatch test classes in parallel, reducing total wall time

#### Scenario: E2E suite falls back to serial when unittest-parallel is absent
- **WHEN** the orchestrator is asked to run the E2E suite AND `unittest-parallel` is NOT importable
- **THEN** the orchestrator falls back to `python -m unittest discover` on the e2e directory, and the suite still runs to completion and exits with the correct pass/fail code

## ADDED Requirements

### Requirement: E2E test classes minimize crew launch overhead
E2E test classes that perform no cross-test mutation of shared crew state SHALL use `setUpClass`/`tearDownClass` to launch exactly one crew container for the lifetime of the class, rather than launching and nuking a container before and after every individual test method.

#### Scenario: Class-level crew for stateless test classes
- **WHEN** an e2e test class contains multiple test methods that all operate on the same crew without mutating shared state between them
- **THEN** the crew is launched once in `setUpClass` and nuked once in `tearDownClass`; no per-test setUp/tearDown launches occur

#### Scenario: TestCrewLifecycle remains per-test
- **WHEN** the `TestCrewLifecycle` class runs
- **THEN** each test method that exercises the full launch→verify→nuke→verify lifecycle gets its own fresh crew via per-test `setUp`/`tearDown`, unchanged from the current behaviour

#### Scenario: TestErrorPaths uses shared crew for stateless errors
- **WHEN** `TestErrorPaths` runs its stateless error-path tests (tests that call a non-existent crew or a non-existent task on the shared crew)
- **THEN** those tests operate against a single shared class-level crew that is launched in `setUpClass` and nuked in `tearDownClass`

#### Scenario: TestErrorPaths per-test throw-away crews for lifecycle-touching tests
- **WHEN** `test_pickup_nonexistent_task`, `test_launch_duplicate_crew`, or `test_nuke_without_confirm` run within `TestErrorPaths`
- **THEN** each of those three tests launches its own short-lived crew with a distinct name and nukes it within the test method body, independent of the shared class-level crew

### Requirement: TestResponseSchemas reuses setUpClass launch result
The `TestResponseSchemas.test_launch_response_shape` test SHALL NOT launch a second independent crew to validate the launch response shape. Instead, it SHALL reuse the crew already launched in `setUpClass` (stored on `cls`) to assert the expected fields, or launch a distinct named crew only when a truly fresh launch is needed for field verification purposes.

#### Scenario: No redundant launch in test_launch_response_shape
- **WHEN** `TestResponseSchemas.test_launch_response_shape` runs
- **THEN** it verifies launch response fields on a crew that is already running (from `setUpClass`) rather than launching an additional crew purely for schema verification

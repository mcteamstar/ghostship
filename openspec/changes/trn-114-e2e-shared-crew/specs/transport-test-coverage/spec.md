## MODIFIED Requirements

### Requirement: e2e suite fixture model

The e2e test suite SHALL use a module-level shared crew as the primary fixture,
launched once per test file rather than once per test class, so that stateless
test classes share a single running crew without incurring per-class launch and
teardown overhead.

Each test file SHALL declare a module-level `SHARED_CREW_ID` constant and
implement `setUpModule` / `tearDownModule` to launch and nuke the shared crew.
Test classes that operate only on task, job, supply, or schema namespaces (with
no cross-class state interference) SHALL read `CREW_ID` from the module-level
`SHARED_CREW_ID` and SHALL NOT implement their own `setUpClass` or
`tearDownClass` that launch or nuke a crew.

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

# Spec Delta

## MODIFIED Requirements

### Requirement: Suite categories
Tests SHALL be organized into at least three categories: unit (no external dependencies — Podman, network, a live install — required), integration (requires a real Podman socket/runtime but not a full ghostship install), and E2E (requires an actual running `ga-transport` and exercises real MCP-tool-level flows like `launch` → `dispatch` → `pickup`). Each category SHALL be independently selectable when running the orchestrator.

#### Scenario: Unit suite runs without Podman
- **WHEN** the unit suite is run in an environment with no Podman binary or socket
- **THEN** all unit tests execute and pass (Podman-dependent test classes/methods remain self-skipping via their existing `skipUnless` guards, as they do today)

#### Scenario: Unit suite runs without bash subprocess support
- **WHEN** the unit suite is run in a container environment where bash subprocesses hang
- **THEN** all unit tests execute and complete without hanging, because no test in the suite spawns an unbounded bash subprocess

#### Scenario: E2E suite is a first-class, if initially small, category
- **WHEN** the orchestrator is asked to run the E2E suite
- **THEN** it runs whatever E2E tests exist under that category (even zero or one today) without special-casing — adding a new E2E test requires no orchestrator changes

## ADDED Requirements

### Requirement: Unit suite runs without marker exclusion
The unit test suite SHALL run to completion under `pytest tests/unit/` with no `-m` marker filter required. No test SHALL depend on a workaround marker (such as `slow`) to prevent hangs or import failures.

#### Scenario: No marker exclusion in CI unit test invocation
- **WHEN** the CI script runs the unit suite
- **THEN** the pytest invocation does NOT pass `-m "not slow"` or any equivalent marker exclusion flag

#### Scenario: pytest.ini declares no workaround markers
- **WHEN** `pytest.ini` is inspected
- **THEN** no `slow` marker (or any marker whose sole purpose was to exclude hanging tests) is declared in the `markers` section

#### Scenario: Full unit suite completes without hangs
- **WHEN** `pytest tests/unit/` is run with no filter flags
- **THEN** pytest exits within a reasonable time (no indefinite hang) and reports a final pass/fail result

### Requirement: Test suite dependencies are complete
All Python packages imported by any test file in `tests/unit/` SHALL be available in the test environment without requiring manual installation steps outside the declared test dependencies.

#### Scenario: starlette importable in test environment
- **WHEN** `pytest tests/unit/test_server.py tests/unit/test_radar_server.py` is run after installing declared test dependencies
- **THEN** no `ModuleNotFoundError` is raised for `starlette` or any of its transitive imports

#### Scenario: httpx importable in test environment
- **WHEN** `pytest tests/unit/` is run after installing declared test dependencies
- **THEN** no `ModuleNotFoundError` is raised for `httpx`

#### Scenario: test_server.py and test_radar_server.py pass with no missing-module errors
- **WHEN** the test venv is built from the declared test dependency list
- **THEN** `test_server.py` and `test_radar_server.py` collect and execute without any `ModuleNotFoundError` at import time

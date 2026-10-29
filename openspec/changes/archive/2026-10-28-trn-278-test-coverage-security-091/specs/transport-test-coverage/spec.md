## MODIFIED Requirements

### Requirement: Critical transport modules have direct unit test coverage

The unit test suite SHALL include direct tests for the following modules that
previously had zero dedicated coverage:
- `transport/security.py` — via `tests/unit/test_security.py`
- `transport/files.py` HMAC machinery — via `tests/unit/test_files.py`
- `transport/container_scripts/inject_policy.py` and `transfer_raw.py` — via
  `tests/unit/test_container_scripts.py`
- `transport/openapi.py` schema generation — via `tests/unit/test_openapi.py`

Each test file SHALL contain at minimum: one passing test per exported function or
security-relevant path, with a named failure mode the test guards.

#### Scenario: test_security.py exists and passes
- **WHEN** `pytest tests/unit/test_security.py` is run
- **THEN** all tests pass with no errors

#### Scenario: test_files.py exists and passes
- **WHEN** `pytest tests/unit/test_files.py` is run
- **THEN** all tests pass with no errors

#### Scenario: test_openapi.py exists and passes
- **WHEN** `pytest tests/unit/test_openapi.py` is run
- **THEN** all tests pass with no errors

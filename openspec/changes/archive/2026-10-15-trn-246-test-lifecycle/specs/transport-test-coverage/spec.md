## ADDED Requirements

### Requirement: lifecycle.py unit test module exists

The test suite SHALL include a dedicated `tests/unit/test_lifecycle.py` module covering `transport/lifecycle.py`. The module SHALL follow the same design principles as other unit modules in `tests/unit/`: dependency injection over module patching, no filesystem I/O, and `FakePodmanClient` for all container runtime calls.

#### Scenario: test_lifecycle.py is present and importable
- **WHEN** `pytest tests/unit/test_lifecycle.py` is executed in an environment with no Podman socket
- **THEN** all tests in the module are collected and run without import errors or skips due to missing Podman

#### Scenario: test_lifecycle.py runs within the existing unit suite
- **WHEN** `pytest tests/unit/` is executed
- **THEN** `test_lifecycle.py` tests are included in the run alongside `test_config.py`, `test_login.py`, `test_registry_lock.py`, and `test_sentinel.py`

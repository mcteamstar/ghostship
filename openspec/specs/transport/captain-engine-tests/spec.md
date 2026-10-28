# transport/captain-engine-tests Specification

## Purpose

Direct unit tests for `transport/captain_engine.py` (807 lines). Previously all
eight exported functions were exercised only indirectly via mocks in
`test_monitors.py`. A regression in any function could silently break the Captain
autopilot lifecycle.

## Requirements

### Requirement: captain_engine.py has direct unit tests

`tests/unit/test_captain_engine.py` SHALL include direct tests for the exported
functions in `transport/captain_engine.py`, covering at minimum:

- `_check_in_memory_pressure` returns correct escalation values given mock host
  memory readings
- `_mail_admiral` does not raise an exception when mail delivery fails
- `_captain_do_status` returns a valid status structure when called for a stopped crew
- `_captain_do_stop` is idempotent — calling it twice does not raise

#### Scenario: _check_in_memory_pressure returns correct level
- **WHEN** `_check_in_memory_pressure` is called with a mock podman client reporting
  low available memory
- **THEN** it returns a non-zero pressure level

#### Scenario: _mail_admiral is failure-safe
- **WHEN** `_mail_admiral` is called and the mail delivery raises an exception
- **THEN** the exception is caught and does not propagate to the caller

#### Scenario: _captain_do_status handles stopped crew
- **WHEN** `_captain_do_status` is called for a crew with status "stopped"
- **THEN** it returns without raising and includes status information

#### Scenario: _captain_do_stop is idempotent
- **WHEN** `_captain_do_stop` is called twice on the same crew
- **THEN** the second call does not raise

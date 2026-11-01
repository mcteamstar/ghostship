# start.sh Shim Specification

## Purpose

`bin/start.sh` is a minimal shell shim that checks prerequisites and delegates
all start logic to `bin/lib/start_main.py` via `exec python3`.

## Requirements

### Requirement: start.sh is a thin prereq-check shim
`bin/start.sh` SHALL contain only prerequisite checks (python3, podman,
podman-compose) and an `exec python3 bin/lib/start_main.py "$@"` delegation.
It SHALL NOT perform any podman, compose, or health-check logic itself.

#### Scenario: start.sh delegates to start_main.py
- **WHEN** `bin/start.sh` is invoked with any arguments
- **THEN** it exec-replaces itself with `python3 bin/lib/start_main.py` passing all arguments unchanged

#### Scenario: start.sh length gate
- **WHEN** the line count of `bin/start.sh` is measured
- **THEN** it is ≤ 40 lines

### Requirement: start.sh rejects missing prerequisites
`bin/start.sh` SHALL exit with a non-zero status and a human-readable error
if `python3`, `podman`, or `podman-compose` is not on PATH.

#### Scenario: python3 missing
- **WHEN** `python3` is not on PATH
- **THEN** `bin/start.sh` exits non-zero with an error naming the missing prerequisite

#### Scenario: podman missing
- **WHEN** `podman` is not on PATH
- **THEN** `bin/start.sh` exits non-zero with an error naming the missing prerequisite

### Requirement: start.sh contains no eval
`bin/start.sh` SHALL NOT contain any `eval` invocation.

#### Scenario: eval absent from start.sh
- **WHEN** `bin/start.sh` is inspected
- **THEN** `grep -c eval bin/start.sh` returns 0

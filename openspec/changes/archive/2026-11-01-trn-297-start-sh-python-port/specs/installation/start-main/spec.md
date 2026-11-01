# Spec Delta

## Purpose

`bin/lib/start_main.py` is the Python entry point for `ghostship start`: it
resolves config, starts the Podman runtime, brings up the compose stack, and
verifies readiness — with no shell eval anywhere in the path.

## ADDED Requirements

### Requirement: start_main.py resolves config before any action
`start_main.py` SHALL resolve all configuration (machine name, dedicated
machine flag, PORT, HOST, TLS mode, compose file path) before invoking any
Podman or compose operation. Unresolvable config SHALL cause a non-zero exit
with a descriptive error.

#### Scenario: Config resolved from ghostship.yaml
- **WHEN** `start_main.py` runs with a valid `ghostship.yaml`
- **THEN** GA_MACHINE_NAME, PORT, HOST, and GA_PORTAL_TLS_MODE are resolved before any podman call

#### Scenario: Missing config file causes early exit
- **WHEN** no config file exists and no defaults apply
- **THEN** `start_main.py` exits non-zero with an error before touching podman

### Requirement: start_main.py starts the Podman runtime via the existing module
`start_main.py` SHALL delegate machine start and socket resolution to
`podman_setup.setup_podman()`. It SHALL NOT reimplement platform-detection
or socket logic inline.

#### Scenario: macOS machine start delegated to podman_setup
- **WHEN** `start_main.py` runs on macOS with a dedicated Podman machine
- **THEN** `podman_setup.setup_podman()` is called and the resolved socket is used for compose

#### Scenario: Linux socket delegated to podman_setup
- **WHEN** `start_main.py` runs on Linux
- **THEN** `podman_setup.setup_podman()` is called and the Linux socket path is used

### Requirement: compose up uses no eval
`start_main.py` SHALL invoke `podman compose up -d` via `subprocess.run` with
compose environment variables passed as an explicit `env` dict. No shell
string interpolation or `eval` SHALL be used to construct the compose command.

#### Scenario: Compose env passed as explicit dict
- **WHEN** `start_main.py` runs compose up
- **THEN** environment variables are passed via `subprocess.run(env=...)`, not via eval or shell interpolation

#### Scenario: Compose failure exits non-zero
- **WHEN** `podman compose up -d` exits non-zero
- **THEN** `start_main.py` exits non-zero and surfaces the compose error to the user

### Requirement: start_main.py verifies readiness through the portal
`start_main.py` SHALL poll the portal `/health` endpoint (via `urllib.request`)
with a bounded retry loop. It SHALL NOT use `curl` or a fixed sleep. Readiness
is declared only when the portal proxies the health check to the transport.

#### Scenario: Portal health check passes within timeout
- **WHEN** the transport and portal start and `/health` responds successfully
- **THEN** `start_main.py` reports success and exits 0

#### Scenario: Health check times out
- **WHEN** `/health` does not respond within the retry window
- **THEN** `start_main.py` exits non-zero with a timeout diagnostic

#### Scenario: Wildcard HOST probed via 127.0.0.1
- **WHEN** HOST is 0.0.0.0 or empty
- **THEN** the health probe targets `http://127.0.0.1:{PORT}/health`

### Requirement: start_main.py is unit-testable without running Podman
`start_main.py` SHALL be structured so that `podman_setup`, `subprocess`, and
`urllib.request` calls can be replaced with mocks in unit tests. No logic that
contacts Podman SHALL run at import time or outside of callable functions.

#### Scenario: Unit tests pass with mocked dependencies
- **WHEN** `pytest tests/unit/test_start_main.py` runs with mocked podman_setup and subprocess
- **THEN** all test cases pass without a running Podman daemon

# testing/podman Specification

## Purpose

Defines verification coverage for podman behavior.

## Requirements

### Requirement: container_exec_stdin unit test coverage
The test suite SHALL include unit tests for `container_exec_stdin` using `socketpair()` to simulate the Unix socket connection, covering: HTTP 101 upgrade handshake; bidirectional relay (stdin→socket, socket→stdout); exit-code extraction from the trailer. Error-path tests SHALL cover `secret_create` / `secret_delete`, `network_disconnect` / `network_rm`, and `volume_create` / `volume_remove` Podman management methods.

#### Scenario: container_exec_stdin completes HTTP 101 upgrade
- **WHEN** `container_exec_stdin` is called with a mock socket that responds with HTTP 101
- **THEN** the upgrade handshake completes and the stdin content is forwarded to the socket

#### Scenario: container_exec_stdin extracts exit code from trailer
- **WHEN** the exec session ends and the socket sends a trailer with exit code
- **THEN** `container_exec_stdin` returns the correct exit code

### Requirement: PodmanClient has dedicated unit tests

`tests/unit/test_podman.py` SHALL exercise PodmanClient with mocked HTTP for container, stdin, archive, network, volume, and error paths. `FakePodmanClient` SHALL match the real client's method signatures and return shapes.

#### Scenario: PodmanClient error paths produce structured exceptions
- **WHEN** the Podman socket returns HTTP 500 for a container operation
- **THEN** PodmanClient raises a typed exception (not a bare dict or silent None)

#### Scenario: FakePodmanClient matches real PodmanClient interface
- **WHEN** FakePodmanClient is instantiated in tests
- **THEN** it exposes the same public methods as PodmanClient with compatible signatures

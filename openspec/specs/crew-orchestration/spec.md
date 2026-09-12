# crew-orchestration Specification

## Purpose

Defines runtime resource management and error handling rules for the crew orchestration layer, including the Podman transport client.

## Requirements

### Requirement: PodmanClient resource and error handling

The `PodmanClient` SHALL narrow exception handling in cleanup operations to expected conditions, properly close HTTP resources, and release client connections on shutdown.

#### Scenario: container_stop — unexpected error propagates
- **WHEN** `container_stop` is called and the Podman API returns an unexpected error (not 404/409)
- **THEN** the error is logged at WARNING level and re-raised (not silently swallowed)

#### Scenario: volume_create — 409 conflict is tolerated, other errors propagate
- **WHEN** `volume_create` is called and the volume already exists (HTTP 409)
- **THEN** the call returns without error
- **WHEN** `volume_create` is called and a socket/permission error occurs
- **THEN** the error propagates (not swallowed)

#### Scenario: httpx2 clients are closed on process exit
- **WHEN** the transport process exits normally
- **THEN** the module-level `httpx2.Client` and `httpx2.AsyncClient` in `podman.py` are closed via `atexit`

#### Scenario: container_exec response is closed after use
- **WHEN** `container_exec` completes reading the response body
- **THEN** the response object is closed (no connection pool leak)

#### Scenario: container_exec_pty_stdin raw socket closed on header-phase error
- **WHEN** `container_exec_pty_stdin` raises during the connect or header-read phase
- **THEN** the raw socket is closed before the exception propagates (no fd leak)

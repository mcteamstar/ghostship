## Purpose

Defines the worker sidecar mechanism and the stopped-crew evac behaviour — how the
transport reads files, git bundles, and git diffs from crew workspaces without requiring
the crew container to be running.

## ADDED Requirements

### Requirement: Worker image exists and is built by install

The `crews/_worker/` directory SHALL contain a `Containerfile` that produces a minimal
image (`localhost/gs-worker:latest`) with Python and git. `install.sh` SHALL build this
image as part of its standard image build sequence.

#### Scenario: Fresh install builds worker image
- **WHEN** `install.sh` is run on a host with no prior ghostship images
- **THEN** `localhost/gs-worker:latest` is present in the ghost-academy image store after install completes

#### Scenario: Missing worker image is reported clearly
- **WHEN** a stopped-crew evac is attempted and `localhost/gs-worker:latest` is not present
- **THEN** the transport returns a 500 error with a message naming the missing image

### Requirement: Evac from stopped crew uses worker sidecar

When a `GET /files/{crew_id}/{path}` request targets a crew whose container is stopped,
the transport SHALL read the file by spawning a disposable worker container that mounts
the crew's workspace volume read-only, without starting the crew container.

#### Scenario: Plain file evac from stopped crew
- **WHEN** `evac` is called for a plain file path on a stopped crew
- **THEN** the file contents are returned with HTTP 200
- **THEN** the crew container remains stopped after the call

#### Scenario: Stopped crew evac does not reset idle timer
- **WHEN** `evac` is called on a stopped crew via the worker path
- **THEN** the crew's last-used timestamp is NOT updated

#### Scenario: Evac from broken crew container
- **WHEN** a crew container exists but cannot be started (corrupt image, OOM)
- **THEN** plain file evac still succeeds via the worker path
- **THEN** the error is not surfaced to the caller for the file read case

### Requirement: Git bundle and diff from stopped crew uses worker sidecar

When a bundle (`?bundle=1`) or diff (`?ref=<ref>`) evac targets a stopped crew, the
transport SHALL perform the git operation inside a worker container with the crew volume
mounted, without starting the crew container.

#### Scenario: Git bundle evac from stopped crew
- **WHEN** `evac` is called with `bundle=1` on a stopped crew
- **THEN** a valid git bundle is returned with HTTP 200
- **THEN** the crew container remains stopped

#### Scenario: Git diff evac from stopped crew
- **WHEN** `evac` is called with a `ref` parameter on a stopped crew
- **THEN** the diff output is returned with HTTP 200
- **THEN** the crew container remains stopped

### Requirement: Live crew evac path is unchanged

When a crew container is running, evac SHALL use the existing `container_archive_get` /
`container_exec` path. The worker sidecar SHALL NOT be used for running containers.

#### Scenario: Evac from running crew does not spawn worker
- **WHEN** `evac` is called and the crew container is running
- **THEN** the file is served via the existing container archive path
- **THEN** no worker container is started

### Requirement: Worker containers are always cleaned up

Worker containers SHALL be started with `--rm` and SHALL be cleaned up on both success
and error paths. A failed or interrupted worker SHALL not leave a dangling container.

#### Scenario: Worker container removed after successful read
- **WHEN** a worker completes a file read successfully
- **THEN** no container named or derived from `gs-worker-*` remains in the container list

#### Scenario: Worker container removed after error
- **WHEN** a worker encounters an error (file not found, git failure)
- **THEN** no worker container remains running or stopped in the container list

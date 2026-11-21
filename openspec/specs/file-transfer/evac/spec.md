# file-transfer/evac Specification

## Purpose

Defines evacuation of workspace files, diffs and Git bundles.

## Requirements

### Requirement: Extracting files and diffs via evac
`evac` SHALL return a presigned URL for a workspace file, tar archive, git diff, or git bundle, and reject paths that escape the workspace. Ordinary refs resolve against `<workspace_root>/repo`; `bundle=True` treats `path` as a repository directory and `ref` as a bundle ref or range. `pack=True` archives a workspace directory as `application/x-tar`.

#### Scenario: Extract a plain file
- **WHEN** `evac` is called with a `path` and no `ref` and `pack=False`
- **THEN** the system returns a presigned URL that streams the file's bytes with a content type guessed from its extension

#### Scenario: Extract a binary plain file without corruption
- **WHEN** a valid presigned URL returned by `evac` with no `ref` and `pack=False` is fetched for a regular file containing bytes that are not valid UTF-8
- **THEN** the response body is byte-for-byte identical to the file in the crew workspace, with no replacement characters or text re-encoding

#### Scenario: Extract a directory as a tar archive
- **WHEN** `evac` is called with `pack=True` and a `path` naming a directory in the workspace
- **THEN** the system returns a presigned URL that, when fetched, streams a tar archive of that directory with Content-Type `application/x-tar`

#### Scenario: Extracted tar archive is valid and extractable
- **WHEN** a valid presigned URL returned by `evac` with `pack=True` is fetched and the response body is saved locally and extracted with `tar`
- **THEN** the extracted contents match the files present in the named workspace directory at the time of the request

#### Scenario: Extract a directory from a stopped crew
- **WHEN** `evac` is called with `pack=True` on a crew whose container is not currently running
- **THEN** the system returns a presigned URL that, when fetched, streams a tar archive of the requested directory using the worker sidecar, without starting the crew container

#### Scenario: pack and bundle are mutually exclusive
- **WHEN** `evac` is called with both `pack=True` and `bundle=True`
- **THEN** the system returns an error and issues no presigned URL

#### Scenario: Extract a git diff
- **WHEN** `evac` is called with a workspace-relative path under `repo/` and a ref that is reachable in the seeded repository
- **THEN** the system returns a presigned URL that streams the git diff between that ref and the current state of the requested repository path, resolved from `<workspace_root>/repo`, instead of the raw file

#### Scenario: Extract a binary-file git diff
- **WHEN** a valid presigned URL returned by `evac` with a `ref` is fetched for a tracked binary file changed relative to that ref in the seeded repository
- **THEN** the response contains git's textual binary-file diff notice, without raw file bytes or UTF-8 replacement characters

#### Scenario: Extract a git bundle of everything
- **WHEN** `evac` is called with `bundle=True`, a `path` naming a directory containing a git repository, and no `ref`
- **THEN** the system returns a presigned URL that streams a git bundle containing every reachable branch and tag in that repository

#### Scenario: Extract a git bundle of a specific ref or range
- **WHEN** `evac` is called with `bundle=True` and a `ref` that is a single ref or a `<ref1>..<ref2>` range reachable in the named repository
- **THEN** the system returns a presigned URL that streams a git bundle scoped to that ref or range

#### Scenario: A caller consumes an extracted bundle
- **WHEN** a caller fetches a valid presigned URL returned by `evac` with `bundle=True` and runs `git clone`/`git fetch` against the downloaded file
- **THEN** the resulting local repository contains the real commits, authorship, and history from the bundled ref(s), not a flattened diff

#### Scenario: Path traversal rejected
- **WHEN** `evac` is called with a `path` containing a `..` segment
- **THEN** the system returns an error and issues no presigned URL

### Requirement: Non-empty path required for evac
The system SHALL reject an `evac` call with an empty or whitespace-only `path` with a 400 Bad Request error and SHALL NOT issue a presigned URL in that case.

#### Scenario: Empty path in evac
- **WHEN** `evac` is called with `path=""` or a path consisting only of whitespace
- **THEN** the system returns an error indicating the path must not be empty and issues no presigned URL

#### Scenario: Non-empty path proceeds normally
- **WHEN** `evac` is called with a non-empty, non-traversal `path`
- **THEN** the system proceeds with signing and returns a presigned URL as normal

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

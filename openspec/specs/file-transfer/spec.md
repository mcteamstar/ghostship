# File Transfer Specification

## Purpose

Move files and directory trees between a crew's isolated workspace and the outside world without routing file bytes through the LLM context, using short-lived presigned URLs served directly by transport.

## Requirements

### Requirement: Extracting files and diffs via evac
The system SHALL return a presigned download URL for a file, a git diff, or a git bundle in a crew's workspace, and SHALL reject any path that attempts to traverse outside the workspace. When a `ref` is supplied with `bundle` unset or `False`, the system SHALL resolve the ref and the requested repository path against the seeded repository at `<workspace_root>/repo` rather than against the workspace root, exactly as today. When `bundle=True`, `path` SHALL instead name a directory containing a git repository (normally `repo`), and `ref` SHALL be treated as the ref, or a `<ref1>..<ref2>` range, to bundle rather than something to diff against.

#### Scenario: Extract a plain file
- **WHEN** `evac` is called with a `path` and no `ref`
- **THEN** the system returns a presigned URL that streams the file's bytes with a content type guessed from its extension

#### Scenario: Extract a binary plain file without corruption
- **WHEN** a valid presigned URL returned by `evac` with no `ref` is fetched for a regular file containing bytes that are not valid UTF-8
- **THEN** the response body is byte-for-byte identical to the file in the crew workspace, with no replacement characters or text re-encoding

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

### Requirement: Supplying files and archives via supply
The system SHALL return a presigned upload URL for injecting a single file, or, with `unpack=True`, a tar/tar.gz archive, or, with `bundle=True`, a git bundle, into a crew's workspace. `unpack` and `bundle` SHALL NOT both be `True` in the same call.

#### Scenario: Supply a single file
- **WHEN** `supply` is called with a destination `path`, `unpack=False`, and `bundle=False`
- **THEN** the system returns a presigned POST URL that writes the request body verbatim to that path, creating intermediate directories as needed

#### Scenario: Supply a directory tree
- **WHEN** `supply` is called with `unpack=True`
- **THEN** the system returns a presigned POST URL that extracts a tar/tar.gz request body at `path` (or the workspace root if `path` is empty or `.`)

#### Scenario: Seed a repository from a bundle
- **WHEN** `supply` is called with `bundle=True` and a destination `path` that does not already exist in the crew's workspace
- **THEN** the system returns a presigned POST URL that, once a git bundle is uploaded to it, clones that bundle into `path` inside the crew, producing a working tree with the bundle's full history

#### Scenario: Reject a bundle delivery into an occupied destination
- **WHEN** the request body posted to a presigned URL from `supply(bundle=True)` targets a `path` that already exists and is non-empty
- **THEN** the clone fails, the existing destination is left unchanged, and the failure is surfaced as an error rather than silently reported as success

#### Scenario: Reject conflicting unpack and bundle modes
- **WHEN** `supply` is called with both `unpack=True` and `bundle=True`
- **THEN** the system returns an error and issues no presigned URL

#### Scenario: Supply a large file beyond the single-argument limit
- **WHEN** a valid presigned URL returned by `supply` receives a file body whose base64 representation would exceed Linux `MAX_ARG_STRLEN`
- **THEN** the upload completes without an `Argument list too long` error and the file bytes are written verbatim to the requested destination

#### Scenario: Supply a large archive beyond the single-argument limit
- **WHEN** a valid presigned URL returned by `supply` with `unpack=True` receives a tar or tar.gz body whose base64 representation would exceed Linux `MAX_ARG_STRLEN`
- **THEN** the upload completes without an `Argument list too long` error and the archive entries are extracted at the requested destination

#### Scenario: Path traversal rejected
- **WHEN** `supply` is called with a `path` containing a `..` segment
- **THEN** the system returns an error and issues no presigned URL

### Requirement: Presigned URL expiry and integrity
The system SHALL sign every `evac` URL with an HMAC over the crew, path, ref, whether `bundle` was requested, and expiry, and SHALL reject requests whose token is expired, missing, or does not match — including a request that replays a validly-signed URL with `bundle` toggled from what was originally signed. `supply`'s `unpack`/`bundle` mode selection is not part of its signed payload, unchanged from `unpack`'s existing behavior today: both modes only affect how the caller's own uploaded bytes get written to a path the caller was already authorized to write to, so mode confusion on the upload side exposes nothing the caller didn't already have.

#### Scenario: Valid token within TTL
- **WHEN** a file request arrives with a signature and expiry that match what the system would generate for that crew/path/ref/bundle combination, and the expiry has not passed
- **THEN** the request is served

#### Scenario: Expired token
- **WHEN** a file request arrives after its `expires` timestamp has passed
- **THEN** the system responds 403 Forbidden regardless of signature validity

#### Scenario: Tampered or invalid signature
- **WHEN** a file request's signature does not match the expected HMAC for its crew/path/ref/bundle/expiry
- **THEN** the system responds 403 Forbidden

#### Scenario: A diff-scoped URL cannot be replayed as a bundle request
- **WHEN** a valid presigned `evac` URL signed with `bundle` unset (or `False`) is requested again with an unsigned `&bundle=1` appended
- **THEN** the recomputed signature does not match, and the system responds 403 Forbidden rather than serving a bundle for a URL only ever authorized for a diff or plain file

### Requirement: Safe archive extraction
The system SHALL extract uploaded tar archives using extraction filtering that blocks writes outside the destination directory (tar-slip protection).

#### Scenario: Archive with a path-escaping member
- **WHEN** an uploaded tar archive contains an entry whose path would resolve outside the destination directory
- **THEN** extraction rejects or strips that entry rather than writing outside the destination

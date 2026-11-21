# File Transfer Specification

## Purpose

Move files and directory trees between a crew's isolated workspace and the outside world without routing file bytes through the LLM context, using short-lived presigned URLs served directly by transport.

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

### Requirement: Supplying files and archives via supply
`supply` SHALL return a presigned URL to upload a file, an archive with `unpack=True`, or a git bundle with `bundle=True`; unpack and bundle SHALL be mutually exclusive. `force` defaults false and, when true for a bundle, SHALL remove the existing destination before cloning. It has no effect outside bundle mode.

#### Scenario: Supply a single file
- **WHEN** `supply` is called with a destination `path`, `unpack=False`, and `bundle=False`
- **THEN** the system returns a presigned POST URL that writes the request body verbatim to that path, creating intermediate directories as needed

#### Scenario: Supply a directory tree
- **WHEN** `supply` is called with `unpack=True`
- **THEN** the system returns a presigned POST URL that extracts a tar/tar.gz request body at `path` (or the workspace root if `path` is empty or `.`)

#### Scenario: Seed a repository from a bundle
- **WHEN** `supply` is called with `bundle=True` and a destination `path` that does not already exist in the crew's workspace
- **THEN** the system returns a presigned POST URL that, once a git bundle is uploaded to it, clones that bundle into `path` inside the crew, producing a working tree with the bundle's full history

#### Scenario: Force re-seed replaces existing destination
- **WHEN** `supply` is called with `bundle=True`, `force=True`, and a destination `path` that already exists and is non-empty in the crew's workspace
- **THEN** the system removes the existing destination, clones the uploaded bundle into that path, and returns success

#### Scenario: Default behaviour (force=False) still rejects occupied destination
- **WHEN** `supply` is called with `bundle=True` and `force=False` (the default) and the destination path already exists and is non-empty
- **THEN** the clone fails and the existing destination is left unchanged (existing behaviour, no change)

#### Scenario: force=True is a no-op for non-bundle modes
- **WHEN** `supply` is called with `force=True` and `bundle=False`
- **THEN** the `force` parameter has no effect; the upload proceeds as a normal plain file write or tar unpack

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
`evac` URLs SHALL HMAC-sign crew, path, ref, bundle, pack, and expiry with SHA-256 truncated to 128 bits; missing, expired, mismatched, or mode-replayed tokens SHALL be rejected. `supply` signatures SHALL include unpack, bundle, and force flags, which the verifier SHALL match; mismatches SHALL return 403.

#### Scenario: Valid token within TTL
- **WHEN** a file request arrives with a 128-bit signature and expiry that match what the system would generate for that crew/path/ref/bundle/pack combination, and the expiry has not passed
- **THEN** the request is served

#### Scenario: Expired token
- **WHEN** a file request arrives after its `expires` timestamp has passed
- **THEN** the system responds 403 Forbidden regardless of signature validity

#### Scenario: Tampered or invalid signature
- **WHEN** a file request's signature does not match the expected HMAC for its crew/path/ref/bundle/pack/expiry
- **THEN** the system responds 403 Forbidden

#### Scenario: A diff-scoped URL cannot be replayed as a bundle request
- **WHEN** a valid presigned `evac` URL signed with `bundle` unset (or `False`) is requested again with an unsigned `&bundle=1` appended
- **THEN** the recomputed signature does not match, and the system responds 403 Forbidden rather than serving a bundle for a URL only ever authorized for a diff or plain file

#### Scenario: A plain-file URL cannot be replayed as a pack request
- **WHEN** a valid presigned `evac` URL signed with `pack=False` is requested again with an unsigned `&pack=1` appended
- **THEN** the recomputed signature does not match, and the system responds 403 Forbidden

#### Scenario: Token signed without force cannot be replayed as a force operation
- **WHEN** a presigned upload URL was generated with `force=False`
- **THEN** the HMAC verification rejects any attempt to interpret that token as authorising a pre-clone deletion

#### Scenario: Upload URL with mode mismatch
- **WHEN** a presigned upload URL was signed with `unpack=False, bundle=False` and a request arrives claiming `unpack=True`
- **THEN** the system responds 403 Forbidden, not performing any extraction

#### Scenario: Upload URL with bundle mode mismatch
- **WHEN** a presigned upload URL was signed with `bundle=True` and a request arrives claiming `bundle=False`
- **THEN** the system responds 403 Forbidden, not treating the body as a plain file write

#### Scenario: HMAC is at least 128 bits long
- **WHEN** the system generates a presigned token for any evac or supply URL
- **THEN** the token's HMAC component is at least 32 hex characters (128 bits)

### Requirement: Safe archive extraction
The system SHALL extract uploaded tar archives using extraction filtering that blocks writes outside the destination directory (tar-slip protection).

#### Scenario: Archive with a path-escaping member
- **WHEN** an uploaded tar archive contains an entry whose path would resolve outside the destination directory
- **THEN** extraction rejects or strips that entry rather than writing outside the destination

### Requirement: Non-empty path required for evac
The system SHALL reject an `evac` call with an empty or whitespace-only `path` with a 400 Bad Request error and SHALL NOT issue a presigned URL in that case.

#### Scenario: Empty path in evac
- **WHEN** `evac` is called with `path=""` or a path consisting only of whitespace
- **THEN** the system returns an error indicating the path must not be empty and issues no presigned URL

#### Scenario: Non-empty path proceeds normally
- **WHEN** `evac` is called with a non-empty, non-traversal `path`
- **THEN** the system proceeds with signing and returns a presigned URL as normal

### Requirement: crew_id format validated in file handler routes
The system SHALL validate that the `crew_id` path segment in `_handle_file_get` and `_handle_file_put` matches the same format constraint enforced by `launch()` — lowercase alphanumeric and hyphens, 1–50 characters — before constructing any filesystem path. Requests with a malformed `crew_id` SHALL be rejected with 400 Bad Request.

#### Scenario: Malformed crew_id in file GET request
- **WHEN** a GET request to the file route carries a `crew_id` containing characters outside lowercase alphanumeric and hyphens, or exceeding 50 characters
- **THEN** the system responds 400 Bad Request and does not attempt to construct a path or read a file

#### Scenario: Malformed crew_id in file PUT request
- **WHEN** a PUT request to the file route carries a malformed `crew_id`
- **THEN** the system responds 400 Bad Request and does not write any file

#### Scenario: Valid crew_id passes format check
- **WHEN** a file route request carries a `crew_id` that is lowercase alphanumeric/hyphens and 1–50 characters
- **THEN** the format check passes and normal processing continues

### Requirement: Crew uploads enforce resource budgets

Supply SHALL enforce configurable request byte limits for all upload modes, archive output byte and member limits, and a storage limit during bundle processing that includes Git metadata and checkout files. Request staging and handoff SHALL use bounded memory.

#### Scenario: Upload exceeds its request budget
- **WHEN** the declared or actual request size exceeds the configured limit
- **THEN** Transport returns HTTP 413 and clears partial staging

#### Scenario: Unpack or checkout exceeds its budget
- **WHEN** an archive or bundle exceeds its processing limits
- **THEN** Transport returns HTTP 413, clears partial staging, and preserves the existing destination

#### Scenario: Client disconnects during request staging
- **WHEN** the client disconnects before the full request is staged
- **THEN** Transport removes partial staging and leaves the destination untouched

#### Scenario: Upload fits its budgets
- **WHEN** an authorized plain upload, unpack, or bundle checkout fits its budgets
- **THEN** it retains existing supply behavior

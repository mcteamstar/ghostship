# file-transfer/supply Specification

## Purpose

Defines upload, archive extraction and resource budgets for supply.

## Requirements

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

### Requirement: Safe archive extraction
The system SHALL extract uploaded tar archives using extraction filtering that blocks writes outside the destination directory (tar-slip protection).

#### Scenario: Archive with a path-escaping member
- **WHEN** an uploaded tar archive contains an entry whose path would resolve outside the destination directory
- **THEN** extraction rejects or strips that entry rather than writing outside the destination

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

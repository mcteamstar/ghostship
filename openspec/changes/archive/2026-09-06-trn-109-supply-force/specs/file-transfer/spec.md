# Delta Spec: file-transfer — force re-seed via supply (TRN-109)

## MODIFIED Requirements

### Requirement: Supplying files and archives via supply
The system SHALL return a presigned upload URL for injecting a single file, or, with `unpack=True`, a tar/tar.gz archive, or, with `bundle=True`, a git bundle, into a crew's workspace. `unpack` and `bundle` SHALL NOT both be `True` in the same call. The `supply` tool SHALL accept an optional `force: bool = False` parameter; when `force=True` and `bundle=True`, the system SHALL remove the existing destination path inside the crew workspace before cloning, allowing a previously-seeded path to be replaced with an updated bundle. `force` SHALL have no effect when `bundle=False`.

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
The system SHALL sign every `evac` URL with an HMAC-SHA256 over the crew, path, ref, whether `bundle` was requested, and expiry, truncated to **128 bits** (32 hex characters), and SHALL reject requests whose token is expired, missing, or does not match — including a request that replays a validly-signed URL with `bundle` toggled from what was originally signed. `supply` presigned upload URLs SHALL include the `mode` field (`unpack`, `bundle`, and `force` flags) in the signed payload; `_verify_file_token` SHALL verify the mode field matches on upload requests. A token signed with `force=False` SHALL be rejected if presented in a context that would trigger `force=True` behaviour, and vice versa. A mismatched or replayed mode SHALL be rejected with 403 Forbidden.

#### Scenario: Valid token within TTL
- **WHEN** a file request arrives with a 128-bit signature and expiry that match what the system would generate for that crew/path/ref/bundle combination, and the expiry has not passed
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

## MODIFIED Requirements

### Requirement: Extracting files and diffs via evac
The system SHALL return a presigned download URL for a file, a git diff, a git
bundle, or a directory tree (tar archive) from a crew's workspace, and SHALL
reject any path that attempts to traverse outside the workspace. When a `ref` is
supplied with `bundle` unset or `False` and `unpack` unset or `False`, the
system SHALL resolve the ref and the requested repository path against the seeded
repository at `<workspace_root>/repo` rather than against the workspace root,
exactly as today. When `bundle=True`, `path` SHALL instead name a directory
containing a git repository (normally `repo`), and `ref` SHALL be treated as the
ref, or a `<ref1>..<ref2>` range, to bundle rather than something to diff against.
When `unpack=True`, `path` SHALL name a directory in the crew workspace and the
system SHALL return a presigned URL that streams the directory contents as a raw
tar archive. `unpack` and `bundle` SHALL NOT both be `True` in the same `evac`
call; the system SHALL return an error without issuing a presigned URL if both
are set.

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

#### Scenario: Extract a directory as a tar archive
- **WHEN** `evac` is called with `unpack=True` and a `path` naming a directory in the crew workspace
- **THEN** the system returns a presigned URL that, when fetched, streams the directory contents as a tar archive with `Content-Type: application/x-tar`

#### Scenario: Unpack and bundle are mutually exclusive on evac
- **WHEN** `evac` is called with both `unpack=True` and `bundle=True`
- **THEN** the system returns an error and issues no presigned URL

#### Scenario: Path traversal rejected
- **WHEN** `evac` is called with a `path` containing a `..` segment
- **THEN** the system returns an error and issues no presigned URL

### Requirement: Presigned URL expiry and integrity
The system SHALL sign every `evac` URL with an HMAC-SHA256 over the crew, path,
ref, whether `bundle` was requested, whether `unpack` was requested, and expiry,
truncated to **128 bits** (32 hex characters), and SHALL reject requests whose
token is expired, missing, or does not match — including a request that replays
a validly-signed URL with `bundle` or `unpack` toggled from what was originally
signed. `supply` presigned upload URLs SHALL include the `mode` field (`unpack`,
`bundle`, and `force` flags) in the signed payload; `_verify_file_token` SHALL
verify the mode field matches on upload requests. A token signed with `force=False`
SHALL be rejected if presented in a context that would trigger `force=True`
behaviour, and vice versa. A mismatched or replayed mode SHALL be rejected with
403 Forbidden.

#### Scenario: Valid token within TTL
- **WHEN** a file request arrives with a 128-bit signature and expiry that match what the system would generate for that crew/path/ref/bundle/unpack combination, and the expiry has not passed
- **THEN** the request is served

#### Scenario: Expired token
- **WHEN** a file request arrives after its `expires` timestamp has passed
- **THEN** the system responds 403 Forbidden regardless of signature validity

#### Scenario: Tampered or invalid signature
- **WHEN** a file request's signature does not match the expected HMAC for its crew/path/ref/bundle/unpack/expiry
- **THEN** the system responds 403 Forbidden

#### Scenario: A diff-scoped URL cannot be replayed as a bundle request
- **WHEN** a valid presigned `evac` URL signed with `bundle` unset (or `False`) is requested again with an unsigned `&bundle=1` appended
- **THEN** the recomputed signature does not match, and the system responds 403 Forbidden rather than serving a bundle for a URL only ever authorized for a diff or plain file

#### Scenario: A plain-file-scoped URL cannot be replayed as an unpack request
- **WHEN** a valid presigned `evac` URL signed with `unpack=False` is requested again with an unsigned `&unpack=1` appended
- **THEN** the recomputed signature does not match, and the system responds 403 Forbidden rather than streaming a tar archive for a URL only ever authorized for a plain file

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

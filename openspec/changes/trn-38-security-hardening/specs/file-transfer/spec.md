## MODIFIED Requirements

### Requirement: Presigned URL expiry and integrity
The system SHALL sign every `evac` URL with an HMAC-SHA256 over the crew, path, ref, whether `bundle` was requested, and expiry, truncated to **128 bits** (32 hex characters), and SHALL reject requests whose token is expired, missing, or does not match — including a request that replays a validly-signed URL with `bundle` toggled from what was originally signed. `supply` presigned upload URLs SHALL include the `mode` field (`unpack` and `bundle` flags) in the signed payload; `_verify_file_token` SHALL verify the mode field matches on upload requests. A mismatched or replayed mode SHALL be rejected with 403 Forbidden.

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

#### Scenario: Upload URL with mode mismatch
- **WHEN** a presigned upload URL was signed with `unpack=False, bundle=False` and a request arrives claiming `unpack=True`
- **THEN** the system responds 403 Forbidden, not performing any extraction

#### Scenario: Upload URL with bundle mode mismatch
- **WHEN** a presigned upload URL was signed with `bundle=True` and a request arrives claiming `bundle=False`
- **THEN** the system responds 403 Forbidden, not treating the body as a plain file write

#### Scenario: HMAC is at least 128 bits long
- **WHEN** the system generates a presigned token for any evac or supply URL
- **THEN** the token's HMAC component is at least 32 hex characters (128 bits)

## ADDED Requirements

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

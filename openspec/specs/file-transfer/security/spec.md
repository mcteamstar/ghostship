# file-transfer/security Specification

## Purpose

Defines file-transfer token, path confinement and audit contracts.

## Requirements

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

### Requirement: Full-length HMAC
The HMAC-SHA256 digest used in presigned URLs MUST use the full 64-character hexdigest.
Truncation to any shorter length is not permitted.

#### Scenario: Presigned URL carries full-length signature
- **WHEN** the transport generates a presigned download or upload URL
- **THEN** the `sig` query parameter is exactly 64 hexadecimal characters

#### Scenario: Truncated signature is rejected
- **WHEN** a request arrives with a `sig` value shorter than 64 characters
- **THEN** the transport returns 403 Forbidden

### Requirement: Operation-typed tokens
Download and upload tokens SHALL be non-interchangeable: the signed payload SHALL include the operation (`get` or `put`). Upload signatures SHALL include the sorted active `bundle`, `force`, and `unpack` flags; signer and verifier SHALL use the same payload. Operation or force mismatches SHALL be rejected.

#### Scenario: Download token rejected on upload endpoint
- **WHEN** a caller presents a valid evac (download) presigned URL to the supply (upload) endpoint
- **THEN** the transport returns 403 Forbidden

#### Scenario: Upload token rejected on download endpoint
- **WHEN** a caller presents a valid supply (upload) presigned URL to the evac (download) endpoint
- **THEN** the transport returns 403 Forbidden

#### Scenario: Correct token accepted on correct endpoint
- **WHEN** a caller presents a valid token to the endpoint it was issued for
- **THEN** the request is accepted and processed

#### Scenario: Token signed with force=False rejected for force=True operation
- **WHEN** a presigned upload URL was generated with `force=False` (flags string does not contain `force`)
- **AND** the verification context would require `force=True` (flags string contains `force`)
- **THEN** the HMAC comparison fails and the transport returns 403 Forbidden

#### Scenario: Token signed with force=True rejected for force=False operation
- **WHEN** a presigned upload URL was generated with `force=True` (flags string contains `force`)
- **AND** the verification context corresponds to `force=False`
- **THEN** the HMAC comparison fails and the transport returns 403 Forbidden

#### Scenario: Matching force flag passes verification
- **WHEN** a presigned upload URL is generated and verified with the same `force` value
- **THEN** HMAC verification passes and the upload proceeds normally

### Requirement: Path canonicalisation
All user-supplied paths MUST be resolved with `Path.resolve()` relative to the crew workspace
root before use. Any path that resolves outside the workspace root MUST be rejected with a 400
error. Checking for `..` components alone is not sufficient. The prefix check MUST append `/`
to the root string (i.e. `startswith(str(root) + "/")`) to prevent adjacent-directory bypass
where a path such as `/workspace-evil/secret` would incorrectly pass a check against root `/workspace`.

#### Scenario: Path traversal via dot-dot is rejected
- **WHEN** a caller supplies a path such as `../../etc/passwd`
- **THEN** the transport returns a 400 error and does not access the file

#### Scenario: Path traversal without dot-dot is rejected
- **WHEN** a caller supplies a path such as `repo/./../../etc/shadow` that resolves outside the workspace
- **THEN** the transport returns a 400 error

#### Scenario: Adjacent-directory path is rejected
- **WHEN** a caller supplies a path that resolves to a directory whose name starts with the workspace root name but is outside it (e.g. root is `/workspace`, path resolves to `/workspace-evil/secret`)
- **THEN** the transport returns a 400 error

#### Scenario: Valid workspace path is accepted
- **WHEN** a caller supplies a path such as `repo/src/main.py` that resolves inside the workspace
- **THEN** the request proceeds normally

### Requirement: `ref` validation
The `ref` parameter in evac requests MUST be validated against `^[a-zA-Z0-9_./-]+$` before
being passed to any git subprocess. Values beginning with `-` MUST be rejected. git invocations
MUST pass `--` before any user-supplied ref as an additional defence-in-depth measure.

#### Scenario: ref beginning with dash is rejected
- **WHEN** a caller supplies `ref` starting with `-` (e.g. `--output=/tmp/pwned`)
- **THEN** the transport returns a validation error without executing any git command

#### Scenario: ref with special characters is rejected
- **WHEN** a caller supplies `ref` containing characters outside `[a-zA-Z0-9_./-]`
- **THEN** the transport returns a validation error

#### Scenario: Valid ref is accepted
- **WHEN** a caller supplies a ref such as `main`, `release/0.2.0`, or a commit hash
- **THEN** the ref is passed to the git subprocess with `--` as an option terminator

### Requirement: Token expiry
Presigned URLs MUST include a server-side expiry timestamp. Expired tokens MUST be rejected
regardless of HMAC validity.

#### Scenario: Expired token is rejected
- **WHEN** a caller presents a presigned URL whose `expires` timestamp is in the past
- **THEN** the transport returns 403 Forbidden even if the HMAC is valid

#### Scenario: Non-expired token is accepted
- **WHEN** a caller presents a presigned URL whose `expires` timestamp is in the future
- **AND** the HMAC is valid
- **THEN** the request is accepted

### Requirement: Valid presigned tokens bypass global Bearer auth at all layers

File-transfer requests with structurally valid `sig` and `expires` parameters SHALL reach the token verifier before Bearer auth; that verifier is the caller-facing gate for GET and PUT/POST. Other middleware SHALL NOT require caller Bearer auth for presigned URLs. `X-Transport-Token` MAY still protect internal Caddy-to-transport requests.

#### Scenario: Presigned download URL fetched without Authorization header
- **WHEN** a valid, non-expired presigned download URL (from `evac`) is fetched
  with `curl` or any HTTP client that does not include an `Authorization` header
- **THEN** the transport serves the file and returns HTTP 200 (or streams the content)
  without returning HTTP 401

#### Scenario: Presigned upload URL posted to without Authorization header
- **WHEN** a valid, non-expired presigned upload URL (from `supply`) is used to
  POST file bytes without an `Authorization` header
- **THEN** the upload succeeds and the transport returns HTTP 200 without returning
  HTTP 401

#### Scenario: Presigned URL with invalid token still rejected
- **WHEN** a request to `/files/` carries a malformed or tampered `sig` parameter
  (or an expired `expires`) but no `Authorization` header
- **THEN** the transport returns HTTP 403 Forbidden (not HTTP 401)

#### Scenario: Bearer auth still required for non-file routes when GA_API_KEY is set
- **WHEN** `GA_API_KEY` is configured and a request arrives for a non-file route
  (e.g. `/mcp`, `/api/spawn`) without a valid `Authorization: Bearer` header
- **THEN** the transport returns HTTP 401 as before — the presigned bypass applies
  only to `/files/` routes

### Requirement: Upload and download presigned bypass is symmetric

The presigned auth bypass SHALL apply identically to upload (PUT/POST to
`/files/`) and download (GET from `/files/`) requests. There SHALL be no
asymmetry where one direction requires the Bearer header and the other does not.

#### Scenario: Upload and download both succeed without Authorization header
- **WHEN** valid presigned URLs for both `supply` (upload) and `evac` (download)
  are used from the same HTTP client without an `Authorization` header
- **THEN** both requests succeed (HTTP 200); neither requires the Bearer header

### Requirement: Presigned URL issuance is audited
Every presigned URL issued by the `supply` or `evac` MCP tools SHALL produce an audit
event via `audit_auth_event`. The event SHALL record at minimum: `action` (`"presign_supply"`
or `"presign_evac"`), `outcome` (`"issued"` on success, `"denied"` on auth failure), and
`source` (the caller's identity key as derived by the transport). The event SHALL NOT
include the presigned URL itself, the HMAC secret, or the caller's raw API key.

#### Scenario: Evac presign emits audit event
- **WHEN** a caller invokes the `evac` MCP tool and a presigned download URL is generated
- **THEN** an audit event with `action="presign_evac"` and `outcome="issued"` is recorded

#### Scenario: Supply presign emits audit event
- **WHEN** a caller invokes the `supply` MCP tool and a presigned upload URL is generated
- **THEN** an audit event with `action="presign_supply"` and `outcome="issued"` is recorded

#### Scenario: Audit event contains no secret material
- **WHEN** a presign audit event is recorded for either tool
- **THEN** the event dict does not contain the HMAC secret, the presigned URL, or any raw
  API key value

### Requirement: Token verification outcome is audited
Every call to `_verify_file_token` (the HMAC token verifier used by the file-download and
file-upload HTTP handlers) SHALL produce an audit event. The event SHALL record `action`
(`"verify_file_token"`), `outcome` (`"valid"` or `"invalid"`), and the operation type
(`get` or `put`). On expiry the `outcome` SHALL be `"expired"`.

#### Scenario: Valid token verification emits audit event
- **WHEN** a file-handler request presents a valid, non-expired presigned token
- **THEN** an audit event with `action="verify_file_token"` and `outcome="valid"` is recorded

#### Scenario: Invalid HMAC emits audit event with outcome=invalid
- **WHEN** a file-handler request presents a token with a bad HMAC signature
- **THEN** an audit event with `action="verify_file_token"` and `outcome="invalid"` is recorded

#### Scenario: Expired token emits audit event with outcome=expired
- **WHEN** a file-handler request presents a token whose `expires` timestamp is in the past
- **THEN** an audit event with `action="verify_file_token"` and `outcome="expired"` is recorded

### Requirement: Upload mutations stay within the crew workspace

Plain uploads, archive unpack, bundle clone, and forced replacement SHALL confine destination mutations to the target crew workspace.

#### Scenario: Upload targets a valid nested workspace path

- **WHEN** a signed upload targets a valid nested destination in the crew workspace
- **THEN** the supported upload operation succeeds as before

#### Scenario: Destination cannot be confined

- **WHEN** the destination or an archive member cannot be safely confined to the workspace
- **THEN** the upload is rejected before destination mutation
- **AND** existing destination data is preserved and staging files are removed

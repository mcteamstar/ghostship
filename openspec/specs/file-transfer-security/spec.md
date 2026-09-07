# File Transfer Security Specification

## Purpose

Security requirements for the file transfer subsystem (supply/evac MCP tools and their
HTTP handlers). The subsystem issues and verifies HMAC-signed presigned URLs for uploading
files into and extracting files from crew workspaces.
## Requirements
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
Download tokens and upload tokens MUST be cryptographically non-interchangeable.
The HMAC payload MUST include the operation type (`get` or `put`) as a prefix.
A token issued for download MUST be rejected when presented for upload, and vice versa.

The `force` flag SHALL be treated as part of the operation type for upload tokens: a token signed with `force=False` MUST NOT be accepted as authorisation for a pre-clone deletion, and a token signed with `force=True` MUST NOT be accepted for a non-destructive upload. The HMAC payload for `supply` presigned upload tokens SHALL include `force` in the sorted flags string alongside `bundle` and `unpack`. The payload format is:

```
{crew_id}:{path}:{expires}:POST::{flags}
```

where `flags` is the sorted, colon-joined set of active boolean options from `{bundle, force, unpack}`. `_sign_upload_url()` and the upload path of `_verify_file_token()` SHALL both include `force` in this flags string so their payloads remain identical.

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


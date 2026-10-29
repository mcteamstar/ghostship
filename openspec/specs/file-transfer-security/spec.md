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

### Requirement: Valid presigned tokens bypass global Bearer auth at all layers

A request to the file-transfer route (`/files/<crew_id>/...`) that carries a
structurally valid `sig` and `expires` query parameter pair SHALL be forwarded
to the presigned token verifier without any prior Bearer auth check. The token
verifier is the sole auth gate for file-transfer requests. An otherwise-valid
presigned URL SHALL NOT return HTTP 401 due to the absence of an
`Authorization: Bearer` header.

This applies to both download (GET) and upload (PUT/POST) requests. The
existing `BearerAuthMiddleware._dispatch_file` path already bypasses Bearer
auth for `/files/` routes; this requirement makes explicit that any additional
auth layer (Caddy proxy, transport-secret middleware, or other middleware)
MUST NOT apply a Bearer requirement to presigned file-transfer requests.

The transport-secret header (`X-Transport-Token`) MAY still be required on
proxied requests from Caddy to the transport backend, since this is an
internal infrastructure credential — not a caller-facing Bearer token.

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

### Requirement: Gateway error response body is redacted before surfacing to callers
Any transport function that surfaces an HTTP error response body from a crew gateway call to an MCP tool caller SHALL redact credential and session material from the body text. At minimum the following patterns SHALL be replaced with a `[redacted]` placeholder before the text reaches any log line or tool response: the crew's session cookie value, `mc_token_<port>=<value>` substrings, any `Authorization: Bearer <value>` substring, and cookie attribute values for `gs_session` and `gs_csrf`. Whitespace SHALL be collapsed and the body SHALL be truncated to a bounded maximum before emission.

#### Scenario: Crew cookie is redacted from gateway error body
- **WHEN** a crew gateway returns an HTTP error response whose body contains the crew's session cookie value
- **THEN** the error text surfaced to the MCP caller does not contain the raw cookie value; it is replaced with `[redacted]`

#### Scenario: mc_token cookie is redacted from gateway error body
- **WHEN** a crew gateway returns an HTTP error response whose body contains a `mc_token_<port>=<value>` substring
- **THEN** the error text surfaced to the MCP caller replaces the value with `mc_token=[redacted]`

#### Scenario: Authorization Bearer value is redacted from gateway error body
- **WHEN** a crew gateway returns an HTTP error response whose body contains an `Authorization: Bearer <token>` substring
- **THEN** the error text surfaced to the MCP caller does not contain the raw token value; the Bearer value is replaced with `[redacted]`

#### Scenario: gs_session cookie value is redacted from gateway error body
- **WHEN** a crew gateway returns an HTTP error response whose body contains a `gs_session=<value>` cookie substring
- **THEN** the error text surfaced to the MCP caller does not contain the raw session token; it is replaced with `[redacted]`

#### Scenario: gs_csrf cookie value is redacted from gateway error body
- **WHEN** a crew gateway returns an HTTP error response whose body contains a `gs_csrf=<value>` cookie substring
- **THEN** the error text surfaced to the MCP caller does not contain the raw CSRF token; it is replaced with `[redacted]`

#### Scenario: Body is truncated to a bounded maximum
- **WHEN** a crew gateway returns an HTTP error response with a body longer than the configured maximum
- **THEN** the body is truncated to that maximum length before being surfaced to the caller, regardless of redaction

#### Scenario: Body with no sensitive material passes through (redacted only)
- **WHEN** a crew gateway returns an HTTP error response whose body contains no credential or session material
- **THEN** the error text surfaced to the caller is the (possibly truncated) raw body text with whitespace collapsed, unchanged by the redaction pass


### Requirement: HMAC sign/verify machinery has direct unit tests

`tests/unit/test_files.py` SHALL include direct tests for the HMAC token signing
and verification functions in `transport/files.py`, covering:

- A valid signed URL verifies successfully
- A tampered signature is rejected
- An expired token is rejected
- A token signed for GET cannot be used on a PUT (mode mismatch)
- Path-traversal attempts are rejected by `_safe_workspace_path`

#### Scenario: Valid signed URL verifies
- **WHEN** a URL is signed with `_sign_file_url` and verified with `_verify_file_token`
- **THEN** verification succeeds and returns the expected payload

#### Scenario: Tampered signature is rejected
- **WHEN** the `sig` query parameter is modified after signing
- **THEN** `_verify_file_token` raises or returns a failure

#### Scenario: Expired token is rejected
- **WHEN** a token is signed with an expiry in the past
- **THEN** `_verify_file_token` rejects it

#### Scenario: Mode mismatch is rejected
- **WHEN** a token signed for GET method is used in a PUT request
- **THEN** `_verify_file_token` rejects it

#### Scenario: Path traversal is rejected
- **WHEN** a path containing `../` or absolute path components is passed to `_safe_workspace_path`
- **THEN** the function raises or returns a safe rejection

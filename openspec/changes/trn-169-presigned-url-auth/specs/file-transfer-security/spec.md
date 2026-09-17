## ADDED Requirements

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

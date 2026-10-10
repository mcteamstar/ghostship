## Why

Presigned download URLs returned by `evac` currently require the caller to also send `Authorization: Bearer <token>` — returning HTTP 401 if the header is absent. This defeats the purpose of presigning: a presigned URL is supposed to be self-authenticating via its `sig` + `expires` query parameters, so any HTTP client (curl, a browser, an S3 SDK) can fetch the file without knowing the transport's API key. The upload path (`supply`) does not require the Bearer header, creating an asymmetry that is both confusing and inconsistent. The bug was discovered when trying to `curl` an evac URL without the header.

## What Changes

- **Download handler auth bypass** — when the incoming request path matches the file-transfer route (`/files/<crew_id>/...`) and the request carries a valid `sig` + `expires` pair, the global Bearer auth middleware SHALL be bypassed. The presigned signature is the credential; no additional auth header is required.
- **Upload handler consistency** — confirm the upload path already bypasses global auth correctly; make the bypass logic shared/unified rather than duplicated or accidentally asymmetric.
- **No change to signing** — the HMAC signing scheme, token expiry, path canonicalisation, and operation-typed token requirements defined in `file-transfer-security` are unchanged. This is purely an auth-order bug: the global middleware fires before the token is verified.

## Capabilities

### New Capabilities
_(none)_

### Modified Capabilities

- `file-transfer-security`: Add an explicit requirement that valid presigned tokens (both download and upload) bypass global Bearer auth. The token verification outcome is the sole auth decision for file-transfer routes.

## Impact

- `transport/` auth middleware or request dispatch — file-transfer routes exempted from global Bearer check when a `sig` + `expires` pair is present; the token verifier becomes the auth gate
- No API surface change — `evac` and `supply` tool signatures unchanged
- No signing scheme change — existing valid presigned URLs continue to work; the fix only affects the auth layer, not the token format

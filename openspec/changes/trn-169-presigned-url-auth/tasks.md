## 1. Diagnose and Document Root Cause

- [x] 1.1 Confirm the exact layer causing the 401: test a presigned evac URL directly against the transport's internal port (bypassing Caddy) to determine whether the Python transport is also rejecting it, or whether it is Caddy-only
- [x] 1.2 Inspect the generated `compose.yml` (or equivalent Caddy config) on the academy host to confirm whether a Bearer auth header requirement is applied at the Caddy level for `/files/` routes

## 2. Fix Caddy Config Generation

- [x] 2.1 Update the Caddy site config generation in `scripts/install.sh` to add a route matcher that exempts requests to `/files/` carrying a `sig` query parameter from any Bearer auth check; the exemption must cover all HTTP methods (GET, POST, PUT)
- [x] 2.2 Ensure the exemption routes the request directly to `ga-transport` without any `forward_auth` sub-request — the Python token verifier is the auth gate for these requests
- [x] 2.3 Verify the matcher syntax is correct for the Caddy version used in the academy deployment

## 3. Harden Python Transport (if needed)

- [x] 3.1 If task 1.1 reveals the Python transport is also incorrectly rejecting presigned requests, fix `BearerAuthMiddleware._dispatch_file` or its call site in `handle_http`
- [x] 3.2 Add an explicit comment to `_dispatch_file` documenting that `/files/` bypasses Bearer auth intentionally — the presigned token is the auth credential

## 4. Tests

- [x] 4.1 Add a test asserting that a GET request to a valid presigned evac URL without an `Authorization` header returns HTTP 200 (not 401)
- [x] 4.2 Add a test asserting that a POST request to a valid presigned supply URL without an `Authorization` header returns HTTP 200 (not 401)
- [x] 4.3 Add a test asserting that a request to `/files/` with an invalid `sig` and no `Authorization` header returns HTTP 403 (not HTTP 401)
- [x] 4.4 Add a test asserting that non-file routes still require Bearer auth when `GA_API_KEY` is set

## 5. Verify and Document

- [ ] 5.1 Re-run `./install.sh` on the academy host and verify presigned evac URLs work without the Bearer header using bare `curl`
- [ ] 5.2 Verify presigned supply URLs work without the Bearer header using bare `curl`
- [x] 5.3 Add a note to `docs/architecture.md` (or the file-transfer section) stating that presigned URLs are self-authenticating and do not require an `Authorization` header

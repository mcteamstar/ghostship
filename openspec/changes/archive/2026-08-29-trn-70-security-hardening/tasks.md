# TRN-70 Tasks — Security Hardening

## Section 1: Critical fixes

- [ ] 1.1 **C-1: Full-length HMAC** — remove `[:32]` from `_sign_file_url`, `_sign_upload_url`, and `_verify_file_token` in `transport/server.py`. All three sites must change together.

- [ ] 1.2 **C-2: `ref` validation** — add `_validate_ref()` helper with regex `^[a-zA-Z0-9_./-]+$`. Call it in `evac()` MCP tool before signing and in `_handle_file_get` before git exec.

- [ ] 1.3 **C-2: git option terminator** — add `--` before `ref` in all git subprocess invocations in `_handle_file_get` (bundle and diff paths).

## Section 2: High fixes

- [ ] 2.1 **H-1: Path canonicalisation** — add `_safe_path(workspace_root, user_path)` helper using `Path.resolve()`. Replace `".." in clean.split("/")` checks in `evac()`, `supply()`, `_handle_file_get`, and `_handle_file_put`.

- [ ] 2.2 **H-2: Operation-typed tokens** — prefix HMAC payloads with `"get:"` in `_sign_file_url` and `"put:"` in `_sign_upload_url`. Update `_verify_file_token` to accept and include the operation parameter. Update `_handle_file_get` and `_handle_file_put` callers.

- [ ] 2.3 **H-3: Auth-off warning** — change `logger.info("Auth disabled...")` to `logger.warning(...)` with a clear message that all endpoints are publicly accessible.

- [ ] 2.4 **H-4: Query string allowlist** — add `_safe_proxy_query()` helper. Apply in the crew gateway proxy handler. Reject strings containing CR/LF/NUL.

## Section 3: Tests

- [ ] 3.1 Test `_sign_file_url` produces a 64-char hex sig (not 32).
- [ ] 3.2 Test that a GET token is rejected when presented to the PUT handler (`operation` mismatch).
- [ ] 3.3 Test that a PUT token is rejected when presented to the GET handler.
- [ ] 3.4 Test `_validate_ref` rejects values starting with `-`, `--`, and containing shell metacharacters. Accepts valid refs (`main`, `release/0.2.0`, `abc123`).
- [ ] 3.5 Test `_safe_path` rejects `../../etc/passwd`, `repo/./../../etc`, accepts `repo/file.py`.
- [ ] 3.6 Test auth-off startup emits a WARNING-level log entry.
- [ ] 3.7 Test `_safe_proxy_query` strips non-allowlisted params and rejects CRLF.

## Section 4: Docs

- [ ] 4.1 Update `docs/configuration.md` — note that `GA_API_KEY` should be set for any non-local deployment; clarify the auth-off warning.
- [ ] 4.2 Update `openspec/specs/file-transfer-security/spec.md` via delta spec sync.

## Section 5: Integration

- [ ] 5.1 Deploy to <host> and run a full supply/evac round-trip to confirm presigned URLs still work after token format change.
- [ ] 5.2 Confirm `evac(ref="--output=/tmp/pwned")` returns a validation error.

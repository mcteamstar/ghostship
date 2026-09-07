## 1. CSRF on logout

- [x] 1.1 In `transport/server.py`, add CSRF token validation to `_handle_dashboard_logout_post()`: read `csrf_token` from the form body and compare against `_dashboard_csrf_token` using `hmac.compare_digest`. Return HTTP 403 on mismatch or missing token (before any session check)
- [x] 1.2 Add test in `tests/unit/test_server.py`: POST to `/dashboard/logout` with valid session but missing/wrong CSRF token returns 403; with valid session and correct CSRF token returns 200

## 2. Server-side redirect fix

- [x] 2.1 In `_handle_dashboard_login_post()` JSON success response, include the sanitised `next` URL: `{"ok": true, "next": _validate_next_url(fd.get("next", "/"))}`
- [x] 2.2 In the login-form JavaScript (inline in `_handle_dashboard_login_ui()`), change the redirect to use `data.next` from the JSON response instead of `fd.get('next')` from the FormData
- [x] 2.3 Add test: POST login with crafted `next=//evil.com` in form body — verify JSON response contains `next: "/"` and not `//evil.com`

## 3. GA_PORTAL_SESSION_TTL_SECS injection

- [x] 3.1 In `scripts/install.sh`, add `GA_PORTAL_SESSION_TTL_SECS` to the compose.yml template env block (near other `GA_PORTAL_*` vars), defaulting to `86400` if unset
- [x] 3.2 Verify: after running `install.sh` with `GA_PORTAL_SESSION_TTL_SECS=3600` in config, the generated `compose.yml` contains `GA_PORTAL_SESSION_TTL_SECS=3600`

## 4. Login throttle — use ASGI client IP not XFF

- [x] 4.1 In `_handle_dashboard_login_post()`, derive the throttle key from `request.client.host` (ASGI connection IP) rather than from `X-Forwarded-For`
- [x] 4.2 Verify existing throttle unit tests still pass; add a test confirming XFF header does not affect the throttle source key

## 5. Corrupt registry — structured error at MCP boundary

- [x] 5.1 In `transport/registry.py`, add a `RegistryCorruptError(RuntimeError)` exception class. Change `_load_registry()` to raise `RegistryCorruptError` instead of re-raising `json.JSONDecodeError` — this gives callers a single named exception to catch rather than an internal JSON parsing detail
- [x] 5.2 In `transport/server.py`, add a top-level `try/except RegistryCorruptError` in each MCP tool handler that calls into the registry (`crews`, `launch`, `dispatch`, `pickup`, `steer`, `nuke`, `schedule`, `supply`, `evac`). Return a structured `{"error": "registry corrupt — crews.json.corrupt preserved for inspection"}` response rather than propagating the exception
- [x] 5.3 Add unit test: mock `_load_registry` to raise `RegistryCorruptError`; call the `crews` MCP tool; verify it returns a structured error response rather than raising

## 6. Validation

- [x] 6.1 Run `openspec validate trn-138-auth-session-hardening`
- [x] 6.2 Run `bash tests/run.sh --unit` — all tests pass
- [ ] 6.3 Deploy to vm23 and run `bash tests/run.sh --e2e`

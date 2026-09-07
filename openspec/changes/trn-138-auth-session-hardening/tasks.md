## 1. CSRF on logout

- [ ] 1.1 In `transport/server.py`, add CSRF token validation to `_handle_dashboard_logout_post()`: read `csrf_token` from the form body and compare against `_dashboard_csrf_token` using `hmac.compare_digest`. Return HTTP 403 on mismatch or missing token (before any session check)
- [ ] 1.2 Add test in `tests/unit/test_server.py`: POST to `/dashboard/logout` with valid session but missing/wrong CSRF token returns 403; with valid session and correct CSRF token returns 200

## 2. Server-side redirect fix

- [ ] 2.1 In `_handle_dashboard_login_post()` JSON success response, include the sanitised `next` URL: `{"ok": true, "next": _validate_next_url(fd.get("next", "/"))}`
- [ ] 2.2 In the login-form JavaScript (inline in `_handle_dashboard_login_ui()`), change the redirect to use `data.next` from the JSON response instead of `fd.get('next')` from the FormData
- [ ] 2.3 Add test: POST login with crafted `next=//evil.com` in form body — verify JSON response contains `next: "/"` and not `//evil.com`

## 3. GA_PORTAL_SESSION_TTL_SECS injection

- [ ] 3.1 In `scripts/install.sh`, add `GA_PORTAL_SESSION_TTL_SECS` to the compose.yml template env block (near other `GA_PORTAL_*` vars), defaulting to `86400` if unset
- [ ] 3.2 Verify: after running `install.sh` with `GA_PORTAL_SESSION_TTL_SECS=3600` in config, the generated `compose.yml` contains `GA_PORTAL_SESSION_TTL_SECS=3600`

## 4. Login throttle — use ASGI client IP not XFF

- [ ] 4.1 In `_handle_dashboard_login_post()`, derive the throttle key from `request.client.host` (ASGI connection IP) rather than from `X-Forwarded-For`
- [ ] 4.2 Verify existing throttle unit tests still pass; add a test confirming XFF header does not affect the throttle source key

## 5. Corrupt registry — structured error at MCP boundary

- [ ] 5.1 In `transport/registry.py`, review what `_load_registry()` raises on corrupt JSON — it currently re-raises `json.JSONDecodeError` after quarantining. Wrap callers at the MCP tool entry points (`crews()`, `dispatch()`, `nuke()`, `launch()`, `pickup()`, `steer()`, `schedule()`, `supply()`, `evac()`) to catch `json.JSONDecodeError` and return a structured error dict rather than propagating an unhandled exception
- [ ] 5.2 Add unit test: mock `_load_registry` to raise `json.JSONDecodeError`; call the `crews` MCP tool; verify it returns a structured error response rather than raising

## 6. Validation

- [ ] 6.1 Run `openspec validate trn-138-auth-session-hardening`
- [ ] 6.2 Run `bash tests/run.sh --unit` — all tests pass
- [ ] 6.3 Deploy to vm23 and run `bash tests/run.sh --e2e`

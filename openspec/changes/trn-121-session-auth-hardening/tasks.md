## 1. Plumbing — module-level security instances

- [ ] 1.1 Add `_dashboard_throttle = _security.Throttle(max_failures=5, window_secs=900)` at module level in `transport/server.py`, directly below the `_gs_session_store` block
- [ ] 1.2 Add `_gs_sessions = _security.SessionStore(lifetime_secs=cfg.ga_portal_session_ttl_secs)` at module level in `transport/server.py`
- [ ] 1.3 Remove `_gs_session_store: dict[str, float]`, `_gs_session_store_lock`, `_gs_session_issue()`, and `_gs_session_valid()` from `transport/server.py`

## 2. Rewrite `_handle_dashboard_login_post`

- [ ] 2.1 At the top of `_handle_dashboard_login_post`, call `_dashboard_throttle.is_locked(account="dashboard", source=_request_source(request))`; return `Response(status_code=429)` if locked — before reading the form body
- [ ] 2.2 After `hmac.compare_digest` fails, call `_dashboard_throttle.record_failure(account="dashboard", source=_request_source(request))` and return 401
- [ ] 2.3 After a successful compare, call `_dashboard_throttle.record_success(account="dashboard", source=_request_source(request))`
- [ ] 2.4 Replace `token = _gs_session_issue()` with `token = _gs_sessions.issue()`
- [ ] 2.5 Build the `Set-Cookie` value conditionally: include `Secure` in the cookie string only when `cfg.ga_portal_tls_mode != "off"`

## 3. Update `_handle_dashboard_auth`

- [ ] 3.1 Replace the `_gs_session_valid(token)` call with `_gs_sessions.validate(token)`

## 4. Add `_handle_dashboard_logout_post`

- [ ] 4.1 Implement `async def _handle_dashboard_logout_post(request: Request) -> Response` that reads `request.cookies.get("gs_session", "")`, returns 401 if `_gs_sessions.validate(token)` is False
- [ ] 4.2 On a valid token, call `_gs_sessions.revoke(token)` and return `Response(status_code=200, content="OK", headers={"Set-Cookie": "gs_session=; Max-Age=0; Expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; SameSite=Lax; Path=/"})`
- [ ] 4.3 Register `("POST", "/dashboard-logout"): _handle_dashboard_logout_post` in the `public_routes` dict inside the `BearerAuthMiddleware(...)` constructor call

## 5. Tests — `test_server.py`

- [ ] 5.1 Add test class `TestDashboardLoginThrottle` covering: throttle blocks after max failures (429), success resets counter, distinct sources tracked independently
- [ ] 5.2 Add test class `TestDashboardSessionStore` covering: issued token validates successfully, revoked token returns 401 on `GET /dashboard-auth`
- [ ] 5.3 Add test class `TestDashboardLogout` covering: valid session revoked and cookie cleared (200 + Set-Cookie Max-Age=0), missing/expired session returns 401
- [ ] 5.4 Add test class `TestDashboardSecureCookie` covering: `Secure` present when `ga_portal_tls_mode != "off"`, `Secure` absent when `ga_portal_tls_mode == "off"`

## 6. Validation

- [ ] 6.1 Run `openspec validate --change trn-121-session-auth-hardening` and confirm no errors
- [ ] 6.2 Run the unit tests: `python -m pytest tests/unit/test_server.py tests/unit/test_trn70_security.py -v` and confirm all pass

## 1. Token generation

- [ ] 1.1 In `transport/server.py`, add a module-level constant `_dashboard_csrf_token: str = secrets.token_hex(32)` near the `_gs_session_store` block (after `secrets` is confirmed imported)

## 2. Embed token in login form

- [ ] 2.1 In `_handle_login_ui`, add `csrf_token_escaped = _security.encode_html_attr(_dashboard_csrf_token)` before the HTML f-string
- [ ] 2.2 Inside the `<form>` in the HTML f-string, add `<input type="hidden" name="csrf_token" value="{csrf_token_escaped}">` immediately after the existing `<input type="hidden" name="next" ...>` line

## 3. Validate token on POST

- [ ] 3.1 In `_handle_dashboard_login_post`, after `await request.form()`, read `provided_csrf = str(form.get("csrf_token", ""))`
- [ ] 3.2 Perform `if not hmac.compare_digest(provided_csrf, _dashboard_csrf_token): return Response(status_code=403)` before the existing API-key comparison

## 4. Unit tests

- [ ] 4.1 In `tests/unit/test_server.py`, add a `DashboardLoginCsrfTests` class (or extend the existing `DashboardLoginPostTests` class with a new section) with setUp/tearDown that saves and restores `server._dashboard_csrf_token`
- [ ] 4.2 Add test: correct CSRF token + correct API key → 200 with `gs_session` cookie
- [ ] 4.3 Add test: missing CSRF token (not in form data) → 403
- [ ] 4.4 Add test: wrong CSRF token → 403
- [ ] 4.5 Add test: wrong CSRF token + correct API key → 403 (not 200 or 401, verifying ordering)
- [ ] 4.6 Add test: `GET /login-ui` response body contains `name="csrf_token"` and the current `_dashboard_csrf_token` value

## 5. Verification

- [ ] 5.1 Run `python -m pytest tests/unit/test_server.py -k "csrf or DashboardLogin" -v` and confirm all new and existing login tests pass
- [ ] 5.2 Run the full unit test suite (`python -m pytest tests/unit/`) and confirm no regressions

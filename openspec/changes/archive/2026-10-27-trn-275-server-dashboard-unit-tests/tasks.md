## 1. test_server.py — server.py utility functions and health handler

- [x] 1.1 Create `tests/unit/test_server.py` with a dual-import shim for
  `transport.server` (package) and `server` (flat container layout), mirroring
  the pattern in `test_auth.py`
- [x] 1.2 Add `TestExtractCrewProxyParts`: test valid crew proxy paths and
  non-matching paths return `None`
- [x] 1.3 Add `TestSanitiseQueryString`: test safe passthrough and stripping of
  control/null characters
- [x] 1.4 Add `TestParseTtlSeconds`: test valid integer strings and invalid/empty
  input returns default
- [x] 1.5 Add `TestJwtExp`: test expiry extraction from a valid JWT, and `None`
  return for malformed tokens (construct a minimal base64-encoded JWT payload
  inline — no real signing needed)
- [x] 1.6 Add `TestCookieNearExpiry`: test `True` for a JWT expiring within the
  threshold and `False` for a fresh JWT
- [x] 1.7 Add `TestHandleHealth`: invoke `_handle_health` via minimal ASGI scope,
  assert HTTP 200 and plain-text `ok` body

## 2. test_dashboard.py — DashboardGate unit tests

- [x] 2.1 Create `tests/unit/test_dashboard.py` with a dual-import shim for
  `transport.dashboard` / `dashboard`, mirroring the pattern in `test_auth.py`
- [x] 2.2 Add `TestValidateNextUrl`: test relative path passthrough,
  protocol-relative rejection, absolute URL rejection, `javascript:` rejection,
  NFKC lookalike rejection, and empty string returning `/`
- [x] 2.3 Add `TestDashboardGateCsrfUniqueness`: construct two `DashboardGate`
  instances (or trigger two session-creation calls on one gate) and assert the
  issued `gs_csrf` tokens are distinct
- [x] 2.4 Add `TestDashboardGateCsrfRejection`: call the login handler with
  a mismatched CSRF token and assert HTTP 403 is returned; call with absent
  token and assert HTTP 403; call with matching token and correct API key and
  assert HTTP 200; call with matching token and wrong API key and assert HTTP 401
- [x] 2.5 Add `TestDashboardGateCookieFlags`: after a successful login, inspect
  the `Set-Cookie` header and assert `SameSite=Lax` is present; if
  `external_url` is `https://...`, assert `Secure` is present; if `http://...`,
  assert `Secure` is absent; assert `HttpOnly` is present

## 3. Verification

- [x] 3.1 Run `pytest tests/unit/ -q` and confirm all existing 912+ tests still
  pass
- [x] 3.2 Run `pytest tests/unit/test_server.py tests/unit/test_dashboard.py -v`
  and confirm all new tests pass
- [x] 3.3 Run coverage: `pytest tests/unit/ --cov=transport.server --cov=transport.dashboard --cov-report=term-missing`
  and confirm `server.py` and `dashboard.py` coverage increases meaningfully
  (target: server.py utility functions covered, dashboard.py >50%)

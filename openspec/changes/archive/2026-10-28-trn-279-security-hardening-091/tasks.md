# Tasks

## 1. Extend gateway error body redaction (H-1)

- [x] 1.1 Add `_BEARER_PATTERN`, `_GS_SESSION_PATTERN`, and `_GS_CSRF_PATTERN` compiled regex constants to `transport/lifecycle.py` alongside the existing `_COOKIE_PATTERN`
- [x] 1.2 Apply the three new patterns in `_gateway_error_detail` before the whitespace-collapse step, replacing each match with `[redacted]`
- [x] 1.3 Add test cases to `tests/unit/test_gateway_error_detail.py` verifying that `Authorization: Bearer <token>`, `gs_session=<value>`, and `gs_csrf=<value>` substrings are redacted from surfaced error text

## 2. Forward_auth port range validation (H-2)

- [x] 2.1 Add `port_base` and `port_range_size` integer parameters to `DashboardGate.__init__` with defaults matching `Config` defaults (64058 and 64 respectively)
- [x] 2.2 In `DashboardGate.handle_auth`, after parsing `port_str` as an integer, validate it falls within `[port_base, port_base + port_range_size)` and return HTTP 400 for values outside the range or non-integer values
- [x] 2.3 Update the `DashboardGate(...)` construction call in `transport/server.py` to pass `cfg.ga_dashboard_port_base` and `cfg.ga_dashboard_port_range_size`
- [x] 2.4 Add test cases to `tests/unit/test_dashboard.py` covering: port below range → 400, port above range → 400, port within range → proceeds, missing port → not rejected, non-integer port → 400

## 3. Rate-limit endpoint matcher test coverage (H-3)

- [x] 3.1 Add `test_dashboard_auth_get_matched` to `TestRateLimitMiddleware` in `tests/unit/test_auth.py` verifying that `GET /dashboard/auth` is matched to the `dashboard_auth` limiter
- [x] 3.2 Add `test_dashboard_login_post_matched` (for the `/dashboard/login` path, not `/login`) to `TestRateLimitMiddleware` if not already present

## 4. Extend heredoc backtick safety check (H-4)

- [x] 4.1 Update `TestHeredocBackticks` in `tests/unit/test_install.py` to also scan `scripts/run.sh` and all `.sh` files under `transport/container_scripts/` for unquoted heredocs containing backticks

## 5. Run tests and verify

- [x] 5.1 Run `bash scripts/run.sh --unit` and confirm all tests pass

# Proposal: TRN-279 — Security Hardening (indy-0.9.1)

## Why

The 0.9.1 sprint introduced new code paths in `steer()` and `transport/tools.py`
that surface gateway error detail to callers and the steer error response previously
raised unhandled exceptions. This change hardens the 0.9.1 additions and
addresses residual low-severity items from the continuous security posture review:
unvalidated port values in the forward_auth endpoint, insufficient redaction
coverage in steer error responses, and missing rate-limit coverage for the
dashboard auth endpoint in the middleware's endpoint matcher.

## What Changes

- **Steer error response redaction** — `_steer_call` now surfaces the gateway's
  response body via `_gateway_error_detail`. The redaction pattern (`_COOKIE_PATTERN`)
  covers `mc_token_<port>=` values and the crew cookie. Extend it to also redact
  any `Authorization: Bearer` value and `gs_session` or `gs_csrf` cookie values
  that could theoretically appear in a gateway error body.

- **`/dashboard/auth` port parameter validation** — `handle_auth` parses the
  `port` query parameter as a plain integer with no range check. Add validation
  that the port falls within the configured dashboard port range
  (`ga_dashboard_port_base` to `ga_dashboard_port_base + ga_dashboard_port_range_size`)
  before looking up the crew; return 400 on out-of-range values.

- **Rate-limit endpoint matcher — `dashboard_auth` path coverage** — the
  `RateLimitMiddleware._match_endpoint` method already has a `dashboard_auth` case for
  `/dashboard/login` and `/dashboard/auth`. Verify and add a unit test confirming
  `/dashboard/auth` (the forward_auth endpoint) is covered, so a burst of synthetic
  auth checks cannot bypass the rate limiter.

- **`_request_source()` XFF audit disambiguation** — `BearerAuthMiddleware` uses
  `_request_source()` for audit events; the function unconditionally prefers
  `X-Forwarded-For`. Annotate the path's intent explicitly in the spec: XFF is
  acceptable for audit-only context (not access control) and is not subject to
  the `GA_TRUSTED_PROXY_CIDR` gate that rate-limit caller-key derivation uses.
  No code change — spec clarification only.

- **`scripts/run.sh` and container scripts — heredoc safety check extension** —
  the `TestHeredocBackticks` test added in 0.9.1 covers `bin/install.sh`. Extend
  the pattern to also scan `scripts/run.sh` and any shell scripts in
  `transport/container_scripts/` for unquoted heredocs with backticks.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `dashboard-session-auth`: Add requirement that the `/dashboard/auth` forward_auth
  endpoint validates the `port` query parameter is within the configured dashboard
  port range before performing a crew lookup; out-of-range values SHALL return HTTP 400.
- `transport/auth-unit-tests`: Add requirement that `_match_endpoint` covers
  `/dashboard/auth` (the forward_auth path) with rate limiting, and that this is
  tested in `tests/unit/test_auth.py`.
- `file-transfer-security`: No change needed — existing redaction requirements
  already cover the file-transfer audit path; this change adds steer-path
  equivalents to the same spec.

  _Revised_: add a new requirement under `file-transfer-security` for the
  gateway error response redaction contract: any function that surfaces gateway
  HTTP error body text to callers SHALL redact `Authorization: Bearer <value>`,
  `gs_session=<value>`, and `gs_csrf=<value>` cookie patterns in addition to
  the existing `mc_token_<port>=` and crew-cookie patterns.

## Impact

- `transport/auth.py` — `_match_endpoint` test coverage; `_request_source` docstring
  annotation
- `transport/lifecycle.py` — `_COOKIE_PATTERN` / `_gateway_error_detail` extended
  redaction
- `transport/dashboard.py` — `handle_auth` port range validation
- `tests/unit/test_auth.py` — `/dashboard/auth` rate-limit coverage test
- `tests/unit/test_install.py` — heredoc backtick check extended to `scripts/` and
  `transport/container_scripts/`
- `tests/unit/test_gateway_error_detail.py` — redaction tests for Bearer and session
  cookie patterns

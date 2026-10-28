# Design: TRN-279 — Security Hardening (indy-0.9.1)

## Context

See `proposal.md — Why` for motivation. Four concrete changes, all low-complexity
and confined to well-understood functions.

## H-1: Extend gateway error body redaction

**Current state:** `_gateway_error_detail` in `transport/lifecycle.py` replaces the
crew cookie and `mc_token_<port>=<value>` patterns. `_COOKIE_PATTERN` is a compiled
regex: `re.compile(r"mc_token_\d+=[^;\s\"']+")`.

**Approach:** Add three more compiled patterns to the module-level constants block:

```
_BEARER_PATTERN      = re.compile(r"Authorization:\s*Bearer\s+\S+", re.IGNORECASE)
_GS_SESSION_PATTERN  = re.compile(r"gs_session=[^;\s\"']+")
_GS_CSRF_PATTERN     = re.compile(r"gs_csrf=[^;\s\"']+")
```

Apply them in sequence inside `_gateway_error_detail` before the whitespace-collapse
step, replacing matches with `[redacted]`. All three are line-local substitutions
with no lookahead — no correctness risk.

The `_response_body` helper in `tools.py` is used only to classify gateway responses
(does the body contain "steer_unsupported"?), never surfaced to callers — no change
needed there.

## H-2: `/dashboard/auth` port range validation

**Current state:** `DashboardGate.handle_auth` parses `port` from the query string as
`int(port_str)` — any valid integer is accepted. Out-of-range values silently fall
through to a `None` crew lookup and return HTTP 200 (the crew-unknown fallback path).

**Approach:** Validate port range immediately after the integer parse. The configured
range is `cfg.ga_dashboard_port_base` to
`cfg.ga_dashboard_port_base + cfg.ga_dashboard_port_range_size` (exclusive). Return
HTTP 400 if the value is outside this range. This requires `handle_auth` to have
access to `ga_dashboard_port_base` and `ga_dashboard_port_range_size` — pass them into
`DashboardGate.__init__` as two new integer fields, alongside the existing
`session_ttl_secs`, `api_key`, and `external_url` arguments.

Callers of `DashboardGate(...)` in `server.py` are the only construction site; update
the constructor call there. Default values for both fields are the existing `Config`
defaults (base=64058, range=64), so all tests that construct `DashboardGate` without
them continue to work.

## H-3: `/dashboard/auth` endpoint coverage in `test_auth.py`

**Current state:** `RateLimitMiddleware._match_endpoint` already routes
`/dashboard/login` and `/dashboard/auth` to the `dashboard_auth` limiter. The unit
tests in `test_auth.py` verify `POST /dashboard/login` is matched but do not have a
corresponding test for `GET /dashboard/auth`.

**Approach:** Add two test cases to `TestRateLimitMiddleware`:
- `test_dashboard_auth_get_matched` — `GET /dashboard/auth` → `dashboard_auth`
- `test_dashboard_login_post_matched` (already exists as `test_login_post_matched`,
  but that covers `/login`, not `/dashboard/login`)

Check whether `test_auth.py` already has a `test_dashboard_login_post_matched`; if
not, add it. Both are trivial `_match_endpoint` calls with no ASGI machinery.

## H-4: Extend `TestHeredocBackticks` to scripts and container_scripts

**Current state:** The test scans only `bin/install.sh`.

**Approach:** Extend the file list to include:
- `scripts/run.sh`
- all `.sh` files under `transport/container_scripts/`

The same backtick-in-unquoted-heredoc regex applies unchanged.

## Non-goals

- Changing the `_response_body` helper (internal classification only, not surfaced).
- Auditing steer outcomes in the security log — steer is an operator-side call, not
  an external auth event.
- Any change to the `x-dashboard-port` header fallback path in `handle_auth` — the
  header is already internal-only (Caddy-injected); port range validation is for the
  externally-accessible query parameter.

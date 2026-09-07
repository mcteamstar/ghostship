## Why

Independent review (2026-09-07) found five auth/session security gaps shipped in the TRN-121 hardening work: logout has no CSRF protection, the login client-side redirect bypasses server-side validation, the session TTL env var is never injected so it silently has no effect, and the rate-limit source IP is spoofable via XFF. Additionally corrupt registry raises an unhandled exception at the MCP tool boundary crashing in-flight requests.

## What Changes

- `transport/server.py` — add CSRF token check to `POST /dashboard/logout` matching the login-form pattern
- `transport/server.py` — fix client-side open-redirect: return sanitised `next` URL in the JSON 200 response body; have the JS redirect from that value rather than from the submitted FormData field
- `scripts/install.sh` — inject `GA_PORTAL_SESSION_TTL_SECS` into the generated `compose.yml` env block so operators can actually configure session TTL
- `transport/auth.py` / `transport/server.py` — use the ASGI client tuple (actual connection IP) for the login rate-limit key instead of trusting `X-Forwarded-For`, or configure Caddy to strip/reset XFF before forwarding
- `transport/registry.py` / `transport/server.py` — catch `json.JSONDecodeError` at MCP tool entry points (or return structured error from `_load_registry()`) so a corrupt registry returns a clean error rather than crashing in-flight MCP requests

## Capabilities

### New Capabilities
- none

### Modified Capabilities
- `dashboard-session-auth`: CSRF on logout, redirect fix — observable behaviour change at `/dashboard/logout` and login redirect
- `installation`: `GA_PORTAL_SESSION_TTL_SECS` now actually injected — env var becomes functional
- `rate-limiting`: source IP resolution changed for login throttle

## Impact

- `transport/server.py` — `_handle_dashboard_logout_post()`: add CSRF check; `_handle_dashboard_login_post()` JS: use server-returned next URL
- `transport/auth.py` — `_request_source()` login path: prefer ASGI client over XFF, or document XFF trust assumption
- `transport/registry.py` — `_load_registry()`: structured error on corrupt JSON
- `scripts/install.sh` — add `GA_PORTAL_SESSION_TTL_SECS` to compose.yml template
- `tests/unit/test_server.py` — tests for CSRF on logout, redirect fix, TTL injection

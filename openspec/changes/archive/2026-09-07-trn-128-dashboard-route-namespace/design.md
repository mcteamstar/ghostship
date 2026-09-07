## Context

See proposal.md — Why.

All four routes currently live at flat paths: `/dashboard-login`, `/dashboard-logout`,
`/dashboard-auth`, and `/login-ui`. They are referenced in:
- `transport/server.py` — route table and inline HTML/JS
- `transport/auth.py` — rate-limit path exception
- `transport/caddy.py` — `forward_auth` rewrite URI
- `scripts/install.sh` — Caddy passthrough list and redirect target

The change is purely mechanical: rename strings. No handler logic changes.

## Goals / Non-Goals

**Goals:**
- Rename the four paths to `/dashboard/login`, `/dashboard/logout`, `/dashboard/auth`, `/dashboard/login-ui`
- Collapse the Caddy passthrough list to `["/health", "/version", "/dashboard/*", "/login", "/login*", "/logout"]`
- Update all internal references (auth.py, caddy.py, server.py HTML/JS, install.sh)
- Update tests, docs, and specs

**Non-Goals:**
- Changing any handler logic or security behaviour
- Adding redirects from old paths to new — no backwards-compat shim needed (this is a private transport endpoint, not a public API)
- Changing device-auth routes (`/login`, `/login*`, `/logout`)

## Decisions

### D1: No backwards-compat redirects

The old paths are internal: only Caddy's own config, the login form's HTML,
and the test suite call them directly. No external client documentation
advertises them as stable. Adding redirects would permanently carry the
old paths as noise; mechanical replacement is cleaner.

### D2: `/dashboard/login-ui` not `/login/ui`

`/login-ui` serves the dashboard login form, not the device auth flow. Moving
it to `/dashboard/login-ui` keeps all dashboard-related endpoints under one
prefix. The kiro-cli device-auth UI (if any) is a separate concern.

### D3: Single glob `/dashboard/*` in Caddy passthrough

Caddy's path matching supports `*` as a suffix glob. One glob rule is simpler
and self-maintaining: future `/dashboard/` sub-routes are automatically
passthrough without a config change.

## Migration Plan

1. Apply mechanical string replacements to the six touch-point files.
2. Update tests to use new paths.
3. Run full unit suite.
4. Deploy — Caddy config regenerated on `install.sh` run, so new passthrough
   and redirect-target take effect immediately on the next deploy.
5. No data migration. In-memory `_gs_sessions` and `_dashboard_throttle` are
   unaffected.

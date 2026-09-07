## Why

The transport's dashboard-related HTTP routes use dash-flattened names (`/dashboard-login`, `/dashboard-logout`, `/dashboard-auth`, `/login-ui`) that obscure their shared purpose and require each path to be listed individually in Caddy's passthrough config. Grouping them under a `/dashboard/` prefix makes the namespace explicit, collapses the Caddy passthrough to a single glob, and aligns with the project's existing `/crews/{id}/ui` and `/crews/{id}/api` patterns.

## What Changes

- **Rename `/dashboard-login` → `/dashboard/login`**: the `POST` endpoint that validates `GA_API_KEY` and issues a `gs_session` cookie.
- **Rename `/dashboard-logout` → `/dashboard/logout`**: the `POST` endpoint that revokes the `gs_session` cookie.
- **Rename `/dashboard-auth` → `/dashboard/auth`**: the `GET` Caddy `forward_auth` target that validates `gs_session` cookies.
- **Rename `/login-ui` → `/dashboard/login-ui`**: the `GET` endpoint that serves the HTML login form.
- **Collapse Caddy passthrough list**: the four separate paths become the single glob `"/dashboard/*"`.
- **Update internal references**: `transport/auth.py` rate-limit path check, `transport/caddy.py` forward_auth rewrite URI, login form JS `fetch` target, redirect-on-success `next` handling, docs, and specs.

**BREAKING**: Any client that hardcodes the old paths (e.g. a browser bookmark, a custom Caddy config, an integration test) must update to the new paths. The kiro-cli device-auth routes (`/login`, `/login*`, `/logout`) are **unchanged**.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `transport/dashboard-auth`: Route paths for `POST /dashboard/login`, `GET /dashboard/auth`, `GET /dashboard/login-ui`, and `POST /dashboard/logout` replace the old dash-separated names. Functional requirements are unchanged; only the URL surface changes.
- `transport/caddy-proxy`: The public passthrough list changes from four explicit paths to the glob `"/dashboard/*"`.
- `transport/dashboard-login-csrf`: The CSRF-protected endpoint is now at `POST /dashboard/login` (path only; behaviour unchanged).

## Impact

- `transport/server.py` — route table, handler docstrings, login form HTML (`action=`, JS `fetch` target)
- `transport/auth.py` — rate-limit path exception check
- `transport/caddy.py` — `forward_auth` rewrite URI
- `scripts/install.sh` — Caddy passthrough list, Caddy redirect-on-401 target
- `tests/unit/test_caddy.py`, `tests/unit/test_server.py` — route path assertions
- `docs/auth.md`, `docs/caddy.md`, `docs/dashboard-proxy.md`, `docs/configuration.md` — URL references
- `openspec/specs/transport/dashboard-auth/spec.md`, `dashboard-login-csrf/spec.md`, `caddy-proxy/spec.md` — spec route references

## 1. Rename routes in transport/server.py

- [x] 1.1 In the `public_routes` dict, rename keys: `(\"POST\", \"/dashboard-login\")` → `(\"POST\", \"/dashboard/login\")`, `(\"POST\", \"/dashboard-logout\")` → `(\"POST\", \"/dashboard/logout\")`, `(\"GET\", \"/dashboard-auth\")` → `(\"GET\", \"/dashboard/auth\")`, `(\"GET\", \"/login-ui\")` → `(\"GET\", \"/dashboard/login-ui\")`
- [x] 1.2 Update all string literals and comments referencing the old paths in handler docstrings and inline comments
- [x] 1.3 In `_handle_login_ui` HTML, update `<form action=\"/dashboard-login\">` → `<form action=\"/dashboard/login\">`
- [x] 1.4 In `_handle_login_ui` HTML, update the JS `fetch('/dashboard-login', ...)` → `fetch('/dashboard/login', ...)`
- [x] 1.5 In `_handle_dashboard_login_post`, update any `next_url` redirect references from `/login-ui` to `/dashboard/login-ui`

## 2. Update transport/auth.py

- [x] 2.1 Update the rate-limit path exception that references `/dashboard-login` and `/dashboard-auth` to use the new paths `/dashboard/login` and `/dashboard/auth`

## 3. Update transport/caddy.py

- [x] 3.1 Update the `forward_auth` rewrite URI from `/dashboard-auth?port=...` to `/dashboard/auth?port=...`

## 4. Update scripts/install.sh

- [x] 4.1 Replace the four-path passthrough list with the single glob: change `\"/dashboard-auth\", \"/dashboard-auth*\", \"/login-ui\", \"/dashboard-login\", \"/dashboard-logout\"` to `\"/dashboard/*\"`
- [x] 4.2 Update any Caddy redirect-on-401 target from `/login-ui` to `/dashboard/login-ui`

## 5. Update tests

- [x] 5.1 In `tests/unit/test_caddy.py`, update all route path assertions and URL strings from the old paths to the new paths
- [x] 5.2 In `tests/unit/test_server.py`, update all route path assertions and URL strings from the old paths to the new paths
- [x] 5.3 Run `bash tests/run.sh --unit` and confirm all tests pass

## 6. Update docs and specs

- [x] 6.1 Update `docs/auth.md`, `docs/caddy.md`, `docs/dashboard-proxy.md`, `docs/configuration.md` — replace all old path references
- [x] 6.2 Update `openspec/specs/transport/dashboard-auth/spec.md`, `dashboard-login-csrf/spec.md`, `caddy-proxy/spec.md` — replace all old path references
- [x] 6.3 Update `CHANGELOG.md` if it references the old paths

## 7. Validate

- [x] 7.1 Run `openspec validate --change trn-128-dashboard-route-namespace` and confirm no errors
- [x] 7.2 Run `bash tests/run.sh --unit` — all tests pass
- [x] 7.3 Deploy to vm23 and run `bash tests/run.sh --e2e` — confirm e2e passes (21 pass, 8 skip)
- [x] 7.4 Smoke-test live: `curl -s http://academy.example.ts.net/dashboard/login-ui` returns the login form HTML
